package com.osiris.shared.presentation

import com.osiris.shared.core.config.AppConfig
import com.osiris.shared.data.DataGraph
import com.osiris.shared.data.storage.PlatformDependencies
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.ExerciseSpec
import com.osiris.shared.presentation.challenge.ChallengeBoardViewModel
import com.osiris.shared.presentation.challenge.ChallengeDetailViewModel
import com.osiris.shared.presentation.challenge.CoursesViewModel
import com.osiris.shared.presentation.community.CommunitiesViewModel
import com.osiris.shared.presentation.community.CommunityDetailViewModel
import com.osiris.shared.presentation.community.RankingsViewModel
import com.osiris.shared.presentation.exercise.ExerciseHubViewModel
import com.osiris.shared.presentation.exercise.ExerciseSessionViewModel
import com.osiris.shared.presentation.progress.ProgressViewModel
import com.osiris.shared.presentation.run.RunViewModel
import com.osiris.shared.presentation.session.LoginViewModel
import com.osiris.shared.presentation.session.OnboardingViewModel
import com.osiris.shared.presentation.session.SessionViewModel
import com.osiris.shared.presentation.settings.SettingsViewModel
import com.osiris.shared.presentation.today.TodayViewModel

/**
 * The composition root both apps create once, at launch, from their platform dependencies:
 *
 *     val graph = AppGraph(AppConfig.fromBuild(), AndroidPlatform.create(context))   // Android
 *     let graph = AppGraph(config: AppConfig.companion.fromBuild(...), platform: IosPlatform.shared.create())  // iOS
 *
 * Each screen asks it for a fresh view model and clears it when the screen goes away.
 */
class AppGraph(val config: AppConfig, platform: PlatformDependencies) {
    val data = DataGraph(config, platform)

    fun session() = SessionViewModel(data.auth)
    fun login() = LoginViewModel(data.auth)
    fun onboarding(inviteToken: String? = null, referralCode: String? = null) =
        OnboardingViewModel(data.auth, data.player, inviteToken, referralCode)
    fun today() = TodayViewModel(data.player)
    fun run(challengeId: Int? = null) = RunViewModel(data.runs, data.challenges, data.player, challengeId)
    fun challengeBoard() = ChallengeBoardViewModel(data.challenges)
    fun challengeDetail(id: Int) = ChallengeDetailViewModel(id, data.challenges, data.player)
    fun courses() = CoursesViewModel(data.challenges)
    fun communities() = CommunitiesViewModel(data.communities)
    fun community(slug: String) = CommunityDetailViewModel(slug, data.communities)
    fun rankings() = RankingsViewModel(data.communities)
    fun progress() = ProgressViewModel(data.player)
    fun settings() = SettingsViewModel(data.auth, data.player, data.privacy, data.exercises)
    fun exerciseHub() = ExerciseHubViewModel(data.exercises)
    fun exerciseSession(spec: ExerciseSpec, catalog: ExerciseCatalog) =
        ExerciseSessionViewModel(spec, catalog, data.exercises, recordingAllowed = config.features.poseRecording)
}
