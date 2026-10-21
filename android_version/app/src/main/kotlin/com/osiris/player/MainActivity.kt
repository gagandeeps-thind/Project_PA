package com.osiris.player

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.osiris.player.ui.navigation.OsirisRoot
import com.osiris.player.ui.theme.OsirisTheme

class MainActivity : ComponentActivity() {
    /** The latest link the OS opened the app with, until the navigator takes it. */
    private var link by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The app renders dark (see OsirisColors); the default style follows the system theme and
        // would draw dark status bar icons on the dark screens whenever the phone is in light mode.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        if (savedInstanceState == null) link = intent?.dataString
        val graph = (application as OsirisApplication).graph
        setContent {
            OsirisTheme {
                OsirisRoot(graph, link, onLinkHandled = { link = null })
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        link = intent.dataString
    }
}
