package com.osiris.player

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.osiris.player.ui.navigation.OsirisRoot
import com.osiris.player.ui.theme.OsirisTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val graph = (application as OsirisApplication).graph
        setContent {
            OsirisTheme {
                OsirisRoot(graph)
            }
        }
    }
}
