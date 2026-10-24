import SwiftUI

/// Asks for camera exercise counting consent: what is analysed, what is kept, how to withdraw.
struct ExerciseConsentSheet: View {
    let onAnswer: (Bool) -> Void

    private static let points: [(icon: String, text: String)] = [
        ("iphone", "Camera images are analysed on this phone only, to find where your joints are. They are never saved or uploaded."),
        ("icloud.and.arrow.up", "Osiris keeps the exercise, your rep count, rep timings and a form score, to verify sets and award XP. This is health information."),
        ("switch.2", "You can withdraw at any time in Settings, and delete your exercise history."),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Count reps with your camera?").font(.title2.bold()).padding(.bottom, 4)
                ForEach(Self.points, id: \.icon) { point in
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: point.icon).foregroundStyle(OsirisColor.secondary).frame(width: 24)
                        Text(point.text)
                    }
                }
                Button { onAnswer(true) } label: { Text("ALLOW").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent)
                    .padding(.top, 8)
                Button { onAnswer(false) } label: { Text("NOT NOW").frame(maxWidth: .infinity) }
            }
            .padding(24)
        }
        .background(OsirisColor.surface)
        .presentationDetents([.large])
    }
}

extension View {
    /// The consent sheet. A swipe down counts as NOT NOW.
    func exerciseConsentSheet(isPresented: Binding<Bool>, onAnswer: @escaping (Bool) -> Void) -> some View {
        sheet(isPresented: Binding(
            get: { isPresented.wrappedValue },
            set: { shown in
                if !shown && isPresented.wrappedValue {
                    isPresented.wrappedValue = false
                    onAnswer(false)
                }
            }
        )) {
            ExerciseConsentSheet { allow in
                isPresented.wrappedValue = false
                onAnswer(allow)
            }
        }
    }

    /// Withdrawing consent: keep the sets already counted, or delete them here and on the server.
    func withdrawExerciseConsentAlert(
        isPresented: Binding<Bool>,
        onKeep: @escaping () -> Void,
        onDelete: @escaping () -> Void
    ) -> some View {
        alert("Stop counting exercises?", isPresented: isPresented) {
            Button("KEEP MY SETS", action: onKeep)
            Button("DELETE MY SETS", role: .destructive, action: onDelete)
            Button("CANCEL", role: .cancel) {}
        } message: {
            Text("Osiris will stop uploading exercise sets. You can also delete your exercise history "
                 + "from Osiris and this phone. XP you already earned stays.")
        }
    }
}

/// The SF Symbol for an exercise, by its catalog key.
func exerciseIcon(_ key: String) -> String {
    switch key {
    case "pushup": return "dumbbell"
    case "squat": return "figure.strengthtraining.functional"
    case "lunge": return "figure.walk"
    case "situp": return "figure.core.training"
    case "jumping_jack": return "figure.mixed.cardio"
    case "high_knees": return "figure.run"
    case "plank": return "minus"
    default: return "figure.gymnastics"
    }
}
