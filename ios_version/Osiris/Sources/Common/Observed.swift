import SwiftUI
import OsirisShared

/// Wraps a shared Kotlin view model for SwiftUI: publishes its state and messages, and clears
/// it when the view goes away. `S` is the Kotlin state type (Kotlin generics reach Swift erased).
@MainActor
final class Observed<VM: SharedViewModel, S: AnyObject>: ObservableObject {
    let vm: VM
    @Published private(set) var state: S
    @Published private(set) var message: UiMessage?
    private var watches: [Watch] = []

    init(_ vm: VM, state flow: KotlinStateFlow) {
        self.vm = vm
        // The current value arrives synchronously, so `state` is set before first render.
        self.state = flow.value as! S
        watches.append(FlowWatchKt.watch(flow) { [weak self] value in self?.state = value as! S })
        watches.append(FlowWatchKt.watchOptional(vm.message) { [weak self] value in self?.message = value as? UiMessage })
    }

    func messageShown() { vm.messageShown() }

    deinit {
        watches.forEach { $0.cancel() }
        vm.clear()
    }
}

typealias KotlinStateFlow = Kotlinx_coroutines_coreStateFlow
