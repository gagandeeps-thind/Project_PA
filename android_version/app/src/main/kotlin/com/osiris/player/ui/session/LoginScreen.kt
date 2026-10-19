package com.osiris.player.ui.session

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.AppGraph

@Composable
fun LoginScreen(graph: AppGraph, onCreateAccount: () -> Unit) {
    val vm = rememberShared { graph.login() }
    val s by vm.state.collectAsStateWithLifecycle()
    Scaffold(containerColor = OsirisColors.Background) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("OSIRIS", style = MaterialTheme.typography.headlineMedium, color = OsirisColors.Primary, fontSize = 40.sp)
            Text("Daily quests for runners and walkers", color = OsirisColors.Muted)
            Spacer(Modifier.height(32.dp))
            OutlinedTextField(
                value = s.email,
                onValueChange = vm::onEmail,
                label = { Text("Email") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = s.password,
                onValueChange = vm::onPassword,
                label = { Text("Password") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                modifier = Modifier.fillMaxWidth(),
            )
            s.error?.let { Text(it, color = OsirisColors.Error, modifier = Modifier.padding(top = 12.dp)) }
            Spacer(Modifier.height(24.dp))
            Button(onClick = vm::submit, enabled = s.canSubmit, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                if (s.busy) CircularProgressIndicator(Modifier.height(20.dp)) else Text("SIGN IN")
            }
            TextButton(onClick = onCreateAccount, modifier = Modifier.padding(top = 8.dp)) { Text("New here? Create an account") }
        }
    }
}
