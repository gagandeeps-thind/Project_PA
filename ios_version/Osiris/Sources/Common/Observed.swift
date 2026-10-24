import SwiftUI
import OsirisShared

/// Wraps a shared Kotlin view model for SwiftUI: publishes its state and messages, and clears
/// it when the view goes away. `S` is the Kotlin state type (Kotlin generics reach Swift erased),
/// a class such as `RunState` or the `any Loadable` protocol. Kotlin delivers every value on the
/// main thread (`Dispatchers.Main`), so the published properties change on the main thread.
final class Observed<VM: SharedViewModel, S>: ObservableObject {
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

    /// Use inside `StateObject(wrappedValue:)`, whose autoclosure then creates the view model
    /// once per screen: `Observed(graph.today()) { $0.state }`. Creating the view model outside
    /// it would build (and leak) a new one on every parent re-render.
    convenience init(_ vm: VM, state: (VM) -> KotlinStateFlow) {
        self.init(vm, state: state(vm))
    }

    func messageShown() { vm.messageShown() }

    deinit {
        watches.forEach { $0.cancel() }
        vm.clear()
    }
}

typealias KotlinStateFlow = Kotlinx_coroutines_coreStateFlow
