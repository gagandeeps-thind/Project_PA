package com.osiris.player.ui.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ScaffoldDefaults
import androidx.compose.runtime.getValue
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import com.osiris.player.ui.design.HudPill
import com.osiris.player.ui.design.LocalTabBarInset
import com.osiris.player.ui.design.RaisedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel

/**
 * Standard screen frame: centered title, optional back arrow and actions, and a snackbar host
 * that shows the view model's messages.
 */
@Composable
fun OsirisScaffold(
    title: String,
    vm: SharedViewModel?,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    val snackbar = remember { SnackbarHostState() }
    if (vm != null) MessageEffect(vm, snackbar)
    val barInset = LocalTabBarInset.current
    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Text(
                        headerText(title),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.ExtraBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
                    }
                },
                actions = actions,
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(containerColor = Color.Transparent),
            )
        },
        snackbarHost = { SnackbarHost(snackbar, Modifier.imePadding().padding(bottom = barInset)) { HudPill(it.visuals.message) } },
        // Under the tab bar the content runs to the bottom of the screen and scrolls behind it.
        contentWindowInsets = if (barInset > 0.dp) WindowInsets(0.dp) else ScaffoldDefaults.contentWindowInsets,
        // Transparent over the app-wide FrostBackground, so every screen sits on the matte backdrop.
        // Transparent alone would make the default content colour black on the dark backdrop.
        containerColor = Color.Transparent,
        contentColor = MaterialTheme.colorScheme.onBackground,
        content = content,
    )
}

/** Shows each view model message once, then tells the view model it was shown. */
@Composable
fun MessageEffect(vm: SharedViewModel, host: SnackbarHostState) {
    val message by vm.message.collectAsStateWithLifecycle()
    LaunchedEffect(message) {
        val m = message ?: return@LaunchedEffect
        host.showSnackbar(m.text, duration = SnackbarDuration.Short)
        vm.messageShown()
    }
}

/** A loading skeleton, an error with a retry button, or the content. */
@Composable
fun <T> LoadableContent(state: Loadable<T>, onRetry: () -> Unit, modifier: Modifier = Modifier, content: @Composable (T) -> Unit) {
    when (state) {
        Loadable.Loading -> LoadingSkeleton(modifier)
        is Loadable.Failed -> Column(
            modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(state.message, color = OsirisColors.Error, textAlign = TextAlign.Center)
            if (state.canRetry) {
                RaisedButton(onClick = onRetry, modifier = Modifier.padding(top = 12.dp)) { Text("Try again") }
            }
        }
        is Loadable.Ready -> content(state.value)
    }
}

/** A header's text: all capitals, with the last word (the key word by convention) in orange. */
fun headerText(text: String): AnnotatedString = buildAnnotatedString {
    val upper = text.uppercase()
    val key = upper.lastIndexOf(' ') + 1
    append(upper.take(key))
    withStyle(SpanStyle(color = OsirisColors.Primary)) { append(upper.drop(key)) }
}

@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier) {
    Text(
        headerText(text),
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.ExtraBold,
        modifier = modifier.fillMaxWidth().padding(start = 16.dp, top = 20.dp, bottom = 6.dp),
    )
}
