package com.osiris.player.ui.session

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.Goal
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.session.OnboardingState
import com.osiris.shared.presentation.session.OnboardingViewModel

@Composable
fun OnboardingScreen(graph: AppGraph, onBack: () -> Unit, inviteToken: String? = null, referralCode: String? = null) {
    val vm = rememberShared { graph.onboarding(inviteToken, referralCode) }
    val s by vm.state.collectAsStateWithLifecycle()
    val back = { if (s.canGoBack) vm.back() else onBack() }
    BackHandler(onBack = back)
    OsirisScaffold("Step ${s.stepNumber} of ${s.stepCount}", vm, onBack = back) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
        ) {
            when (s.step) {
                OnboardingState.Step.GOAL -> GoalStep(s, vm)
                OnboardingState.Step.CONSENT -> ConsentStep(s, vm)
                OnboardingState.Step.ACCOUNT -> AccountStep(s, vm)
            }
        }
    }
}

@Composable
private fun GoalStep(s: OnboardingState, vm: OnboardingViewModel) {
    Text("What do you want from Osiris?", style = MaterialTheme.typography.headlineSmall)
    Text("We use this to size your daily quest. You can change it any time.", color = OsirisColors.Muted)
    Spacer(Modifier.height(20.dp))
    for (goal in Goal.entries) {
        val selected = s.goal == goal
        FrostCard(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            onClick = { vm.selectGoal(goal) },
            contentPadding = 0.dp,
            fill = if (selected) OsirisColors.Primary.copy(alpha = 0.22f) else null,
        ) {
            ListItem(
                headlineContent = { Text(goal.label, fontWeight = FontWeight.SemiBold) },
                supportingContent = { Text(goal.description) },
                trailingContent = { if (selected) Icon(Icons.Filled.CheckCircle, null, tint = OsirisColors.Secondary) },
                colors = ListItemDefaults.colors(containerColor = Color.Transparent),
            )
        }
    }
    Spacer(Modifier.height(24.dp))
    Button(onClick = vm::next, modifier = Modifier.fillMaxWidth()) { Text("CONTINUE") }
}

@Composable
private fun ConsentStep(s: OnboardingState, vm: OnboardingViewModel) {
    Text("Your location, your control", style = MaterialTheme.typography.headlineSmall)
    Spacer(Modifier.height(8.dp))
    Text("Runs need it to be verified. You can change this later in Settings.", color = OsirisColors.Muted)
    Spacer(Modifier.height(16.dp))
    Row(Modifier.fillMaxWidth().clickable { vm.setLocationConsent(!s.locationConsent) }, verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = s.locationConsent, onCheckedChange = vm::setLocationConsent)
        Text("Allow location during runs")
    }
    Spacer(Modifier.height(24.dp))
    Button(onClick = vm::next, modifier = Modifier.fillMaxWidth()) { Text("CONTINUE") }
}

@Composable
private fun AccountStep(s: OnboardingState, vm: OnboardingViewModel) {
    Text("Create your account", style = MaterialTheme.typography.headlineSmall)
    Spacer(Modifier.height(16.dp))
    Field("Name others see", s.displayName, vm::onName, s.fieldErrors[Registration.FIELD_NAME])
    Field("Email", s.email, vm::onEmail, s.fieldErrors[Registration.FIELD_EMAIL], KeyboardType.Email)
    Field("Password", s.password, vm::onPassword, s.fieldErrors[Registration.FIELD_PASSWORD], KeyboardType.Password, secret = true)
    Field("Invite code (optional)", s.referralCode, vm::onReferralCode, null)
    Spacer(Modifier.height(24.dp))
    Button(onClick = vm::create, enabled = !s.busy, modifier = Modifier.fillMaxWidth().height(52.dp)) {
        Text(if (s.busy) "CREATING…" else "START MY FIRST QUEST")
    }
}

@Composable
private fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    error: String?,
    type: KeyboardType = KeyboardType.Text,
    secret: Boolean = false,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        isError = error != null,
        supportingText = if (error != null) { { Text(error) } } else null,
        visualTransformation = if (secret) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = type),
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    )
}
