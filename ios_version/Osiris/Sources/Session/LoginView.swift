import SwiftUI
import OsirisShared

struct LoginView: View {
    let graph: AppGraph
    @StateObject private var model: Observed<LoginViewModel, LoginState>

    init(graph: AppGraph) {
        self.graph = graph
        _model = StateObject(wrappedValue: Observed(graph.login()) { $0.state })
    }

    var body: some View {
        let s = model.state
        Form {
            Section {
                TextField("Email", text: Binding(get: { s.email }, set: { model.vm.onEmail(value: $0) }))
                    .keyboardType(.emailAddress)
                    .textContentType(.username)
                    .textInputAutocapitalization(.never)
                SecureField("Password", text: Binding(get: { s.password }, set: { model.vm.onPassword(value: $0) }))
                    .textContentType(.password)
            }
            if let error = s.error {
                Text(error).foregroundStyle(OsirisColor.error)
            }
            Button(s.busy ? "SIGNING IN…" : "SIGN IN") { model.vm.submit() }
                .disabled(!s.canSubmit)
            NavigationLink("New here? Create an account") { OnboardingView(graph: graph) }
        }
        .navigationTitle("OSIRIS")
    }
}
