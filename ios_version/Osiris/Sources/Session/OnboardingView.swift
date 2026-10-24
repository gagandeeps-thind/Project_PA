import SwiftUI
import OsirisShared

/// Three steps: goal, location consent, account. On success the session changes and the root
/// shows Today, so there is nothing to navigate here.
struct OnboardingView: View {
    @StateObject private var model: Observed<OnboardingViewModel, OnboardingState>
    @Environment(\.dismiss) private var dismiss

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.onboarding(inviteToken: nil, referralCode: nil)) { $0.state })
    }

    var body: some View {
        let s = model.state
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                switch s.step {
                case .goal: goalStep(s)
                case .consent: consentStep(s)
                default: accountStep(s)
                }
            }
            .padding(24)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(OsirisColor.background)
        .navigationTitle("Step \(s.stepNumber) of \(s.stepCount)")
        .navigationBarTitleDisplayMode(.inline)
        // Back walks the steps first, then leaves sign-up.
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { if s.canGoBack { model.vm.back() } else if !s.busy { dismiss() } } label: {
                    Image(systemName: "chevron.backward")
                }
                .accessibilityLabel("Back")
            }
        }
        .messages(model)
    }

    @ViewBuilder private func goalStep(_ s: OnboardingState) -> some View {
        Text("What do you want from Osiris?").font(.title2.bold())
        Text("We use this to size your daily quest. You can change it any time.").foregroundStyle(OsirisColor.muted)
        ForEach(Goal.entries, id: \.wire) { goal in
            let selected = s.goal == goal
            Button { model.vm.selectGoal(goal: goal) } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(goal.label).fontWeight(.semibold)
                        Text(goal.description_).font(.subheadline).foregroundStyle(OsirisColor.muted)
                    }
                    Spacer()
                    if selected { Image(systemName: "checkmark.circle.fill").foregroundStyle(OsirisColor.secondary) }
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(selected ? OsirisColor.primary.opacity(0.25) : OsirisColor.surface, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(selected ? .isSelected : [])
        }
        continueButton
    }

    @ViewBuilder private func consentStep(_ s: OnboardingState) -> some View {
        Text("Your location, your control").font(.title2.bold())
        Text("Runs need it to be verified. You can change this later in Settings.").foregroundStyle(OsirisColor.muted)
        // Never pre-ticked: the player turns it on.
        Toggle("Allow location during runs", isOn: Binding(get: { s.locationConsent }, set: { model.vm.setLocationConsent(granted: $0) }))
            .padding(.vertical, 8)
        continueButton
    }

    @ViewBuilder private func accountStep(_ s: OnboardingState) -> some View {
        Text("Create your account").font(.title2.bold())
        field("Name others see", s.displayName, error: s.fieldErrors[Registration.companion.FIELD_NAME]) { model.vm.onName(v: $0) }
            .textContentType(.nickname)
        field("Email", s.email, error: s.fieldErrors[Registration.companion.FIELD_EMAIL]) { model.vm.onEmail(v: $0) }
            .keyboardType(.emailAddress)
            .textContentType(.username)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
        field("Password", s.password, error: s.fieldErrors[Registration.companion.FIELD_PASSWORD], secure: true) { model.vm.onPassword(v: $0) }
            .textContentType(.newPassword)
        field("Invite code (optional)", s.referralCode, error: nil) { model.vm.onReferralCode(v: $0) }
            .textInputAutocapitalization(.characters)
            .autocorrectionDisabled()
        Button { model.vm.create() } label: {
            Text(s.busy ? "CREATING…" : "START MY FIRST QUEST").frame(maxWidth: .infinity, minHeight: 36)
        }
        .buttonStyle(.borderedProminent)
        .disabled(s.busy)
        .padding(.top, 12)
    }

    private var continueButton: some View {
        Button { model.vm.next() } label: { Text("CONTINUE").frame(maxWidth: .infinity, minHeight: 36) }
            .buttonStyle(.borderedProminent)
            .padding(.top, 12)
    }

    private func field(
        _ label: String,
        _ value: String,
        error: String?,
        secure: Bool = false,
        onChange: @escaping (String) -> Void
    ) -> some View {
        let binding = Binding(get: { value }, set: onChange)
        return VStack(alignment: .leading, spacing: 4) {
            Group {
                if secure { SecureField(label, text: binding) } else { TextField(label, text: binding) }
            }
            .padding(12)
            .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(error == nil ? Color.clear : OsirisColor.error))
            if let error { Text(error).font(.caption).foregroundStyle(OsirisColor.error) }
        }
    }
}
