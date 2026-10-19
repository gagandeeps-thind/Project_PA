import MapKit
import SwiftUI
import OsirisShared

/// The run map, the iOS counterpart of the Android OsmMap: the challenge course with its green
/// start and red finish zones, the recorded trace, nearby challenge markers and the player.
///
/// Overlays are replaced only when their data changes, so a new GPS fix redraws the trace alone.
struct RunMap: UIViewRepresentable {
    var position: LatLng?
    var course: CourseRoute?
    var trace: [LatLng] = []
    var nearby: [ChallengeSummary] = []
    /// Keep the player centred (while recording).
    var follow = false
    /// Fit the course and fix the view, for the small preview on a challenge page.
    var preview = false
    /// Tapping a marker opens its challenge; nil while recording, so a run is not interrupted.
    var onChallenge: ((Int32) -> Void)?

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator
        map.showsUserLocation = !preview
        map.pointOfInterestFilter = .excludingAll
        map.overrideUserInterfaceStyle = .dark
        if preview {
            map.isScrollEnabled = false
            map.isZoomEnabled = false
            map.isRotateEnabled = false
            map.isPitchEnabled = false
        }
        return map
    }

    func updateUIView(_ map: MKMapView, context: Context) {
        let c = context.coordinator
        c.onChallenge = onChallenge

        let route = course?.route ?? []
        if c.courseKey != route.count {
            c.courseKey = route.count
            map.removeOverlays(map.overlays.filter { c.isCourse($0) })
            if route.count >= 2, let course {
                let line = MKPolyline(coordinates: route.map(Self.coordinate), count: route.count)
                line.title = Coordinator.courseLine
                let radius = max(course.startRadiusM, 15)
                let start = MKCircle(center: Self.coordinate(route.first!), radius: radius)
                start.title = Coordinator.startZone
                let finish = MKCircle(center: Self.coordinate(route.last!), radius: radius)
                finish.title = Coordinator.finishZone
                map.addOverlays([line, start, finish])
                if preview || position == nil {
                    map.setVisibleMapRect(line.boundingMapRect, edgePadding: UIEdgeInsets(top: 24, left: 24, bottom: 24, right: 24), animated: false)
                }
            }
        }

        if c.traceCount != trace.count {
            c.traceCount = trace.count
            if let old = c.trace { map.removeOverlay(old) }
            c.trace = nil
            if trace.count >= 2 {
                let line = MKPolyline(coordinates: trace.map(Self.coordinate), count: trace.count)
                line.title = Coordinator.traceLine
                map.addOverlay(line)
                c.trace = line
            }
        }

        let ids = nearby.map(\.id)
        if c.nearbyIds != ids {
            c.nearbyIds = ids
            map.removeAnnotations(map.annotations.filter { $0 is ChallengePin })
            map.addAnnotations(nearby.map(ChallengePin.init))
        }

        if !preview, let position {
            let here = Self.coordinate(position)
            if follow {
                map.setCenter(here, animated: true)
            } else if !c.centred {
                c.centred = true
                map.setRegion(MKCoordinateRegion(center: here, latitudinalMeters: 800, longitudinalMeters: 800), animated: false)
            }
        }
    }

    private static func coordinate(_ p: LatLng) -> CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: p.lat, longitude: p.lng)
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        static let courseLine = "course"
        static let startZone = "start"
        static let finishZone = "finish"
        static let traceLine = "trace"

        var courseKey = -1
        var traceCount = 0
        var trace: MKPolyline?
        var nearbyIds: [Int32] = []
        var centred = false
        var onChallenge: ((Int32) -> Void)?

        func isCourse(_ overlay: MKOverlay) -> Bool {
            let title = overlay.title ?? nil
            return title == Self.courseLine || title == Self.startZone || title == Self.finishZone
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let line = overlay as? MKPolyline {
                let r = MKPolylineRenderer(polyline: line)
                r.strokeColor = UIColor(line.title == Self.traceLine ? OsirisColor.primary : OsirisColor.secondary.opacity(0.7))
                r.lineWidth = line.title == Self.traceLine ? 5 : 6
                return r
            }
            if let circle = overlay as? MKCircle {
                let r = MKCircleRenderer(circle: circle)
                let color = UIColor(circle.title == Self.startZone ? OsirisColor.success : OsirisColor.error)
                r.fillColor = color.withAlphaComponent(0.25)
                r.strokeColor = color
                r.lineWidth = 2
                return r
            }
            return MKOverlayRenderer(overlay: overlay)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let pin = annotation as? ChallengePin else { return nil }
            let view = mapView.dequeueReusableAnnotationView(withIdentifier: "challenge") as? MKMarkerAnnotationView
                ?? MKMarkerAnnotationView(annotation: pin, reuseIdentifier: "challenge")
            view.annotation = pin
            view.glyphImage = UIImage(systemName: "trophy.fill")
            view.markerTintColor = UIColor(OsirisColor.warning)
            view.canShowCallout = true
            view.rightCalloutAccessoryView = UIButton(type: .detailDisclosure)
            return view
        }

        func mapView(_ mapView: MKMapView, annotationView view: MKAnnotationView, calloutAccessoryControlTapped control: UIControl) {
            guard let pin = view.annotation as? ChallengePin else { return }
            onChallenge?(pin.challengeId)
        }
    }
}

/// A nearby challenge on the map; the callout names it and its course length.
final class ChallengePin: NSObject, MKAnnotation {
    let challengeId: Int32
    let coordinate: CLLocationCoordinate2D
    let title: String?
    let subtitle: String?

    init(_ c: ChallengeSummary) {
        challengeId = c.id
        coordinate = CLLocationCoordinate2D(latitude: c.markerLat, longitude: c.markerLng)
        title = c.title
        subtitle = Format.shared.distance(metres: c.courseDistanceM)
    }
}
