import CoreLocation
import OsirisShared

/// Core Location for runs, the iOS counterpart of the Android LocationClient: best accuracy, a
/// 5 m distance filter, and each fix stamped with `CLLocation.timestamp` (when it was measured).
///
/// Recording keeps updates running with the screen off: [setRecording] turns on background
/// updates, which the `location` background mode in Info.plist allows. Created on the main
/// thread, so Core Location calls the delegate there too.
final class LocationTracker: NSObject, ObservableObject {
    private let manager = CLLocationManager()
    private var onFix: ((LocationFix) -> Void)?
    private var onUnavailable: ((AppError) -> Void)?
    private var waiting: [CheckedContinuation<LatLng?, Never>] = []
    private var updating = false

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = 5
        manager.activityType = .fitness
        manager.pausesLocationUpdatesAutomatically = false
    }

    private var authorized: Bool {
        let status = manager.authorizationStatus
        return status == .authorizedWhenInUse || status == .authorizedAlways
    }

    /// Streams every fix to [onFix] until [stop], asking for permission first when needed.
    func start(onFix: @escaping (LocationFix) -> Void, onUnavailable: @escaping (AppError) -> Void) {
        self.onFix = onFix
        self.onUnavailable = onUnavailable
        switch manager.authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            beginUpdates()
        default:
            onUnavailable(IosSupport.shared.locationOff())
        }
    }

    func stop() {
        setRecording(false)
        manager.stopUpdatingLocation()
        updating = false
        onFix = nil
        onUnavailable = nil
    }

    /// While a run records, updates continue in the background, with the system's blue
    /// location indicator showing.
    func setRecording(_ on: Bool) {
        guard authorized else { return }
        manager.allowsBackgroundLocationUpdates = on
        manager.showsBackgroundLocationIndicator = on
    }

    /// One position, or nil without permission. With [askIfNeeded] false it never prompts.
    /// Main-actor bound, so it shares `waiting` with the delegate callbacks on the main thread.
    @MainActor func currentPosition(askIfNeeded: Bool) async -> LatLng? {
        if manager.authorizationStatus == .notDetermined {
            guard askIfNeeded else { return nil }
            manager.requestWhenInUseAuthorization()
        } else if !authorized {
            return nil
        }
        if let cached = manager.location, -cached.timestamp.timeIntervalSinceNow < 120 {
            return LatLng(lat: cached.coordinate.latitude, lng: cached.coordinate.longitude)
        }
        return await withCheckedContinuation { continuation in
            waiting.append(continuation)
            if authorized { manager.requestLocation() }
        }
    }

    private func beginUpdates() {
        guard !updating else { return }
        updating = true
        // A fast first position from the cache, so the map centres at once. It was measured
        // before the run starts, so the shared run code never records it as a route point.
        if let cached = manager.location { onFix?(Self.fix(cached)) }
        manager.startUpdatingLocation()
    }

    private func resumeWaiting(_ position: LatLng?) {
        let pending = waiting
        waiting = []
        pending.forEach { $0.resume(returning: position) }
    }

    private static func fix(_ l: CLLocation) -> LocationFix {
        IosSupport.shared.locationFix(
            lat: l.coordinate.latitude,
            lng: l.coordinate.longitude,
            accuracyM: l.horizontalAccuracy,
            speedMps: l.speed,
            altitudeM: l.altitude,
            hasAltitude: l.verticalAccuracy > 0,
            measuredAtEpochMs: Int64((l.timestamp.timeIntervalSince1970 * 1000).rounded())
        )
    }
}

extension LocationTracker: CLLocationManagerDelegate {
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if authorized {
            if onFix != nil { beginUpdates() }
            if !waiting.isEmpty { manager.requestLocation() }
        } else if manager.authorizationStatus != .notDetermined {
            onUnavailable?(IosSupport.shared.locationOff())
            resumeWaiting(nil)
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        for l in locations where l.horizontalAccuracy >= 0 {
            onFix?(Self.fix(l))
        }
        if let last = locations.last {
            resumeWaiting(LatLng(lat: last.coordinate.latitude, lng: last.coordinate.longitude))
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // "Location unknown" is transient: Core Location keeps trying.
        let code = (error as? CLError)?.code
        if code == .denied {
            onUnavailable?(IosSupport.shared.locationOff())
            resumeWaiting(nil)
        } else if code != .locationUnknown {
            resumeWaiting(nil)
        }
    }
}
