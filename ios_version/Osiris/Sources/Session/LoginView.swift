import SwiftUI
import OsirisShared

struct LoginView: View {
    @StateObject private var model: Observed<LoginViewModel, LoginState>

    init(graph: AppGraph) {
        let vm = graph.login()
        _model = StateObject(wrappedValue: Observed(vm, state: vm.state))
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
        }
        .navigationTitle("OSIRIS")
    }
}
