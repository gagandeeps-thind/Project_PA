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
        // The app is always dark; the default style follows the system theme and would draw dark
        // status bar icons on the dark screens whenever the phone is in light mode.
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
