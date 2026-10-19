package com.osiris.player

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.osiris.player.ui.navigation.OsirisRoot
import com.osiris.player.ui.theme.OsirisTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The app is always dark, so keep light status and navigation bar icons even when the
        // phone is in light mode (the default style would pick dark icons there).
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        val graph = (application as OsirisApplication).graph
        setContent {
            OsirisTheme {
                OsirisRoot(graph)
            }
        }
    }
}
