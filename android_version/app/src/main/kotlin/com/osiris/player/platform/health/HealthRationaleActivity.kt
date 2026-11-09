package com.osiris.player.platform.health

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import com.osiris.player.OsirisApplication
import com.osiris.player.ui.theme.OsirisTheme

/** Health Connect opens this to show players why Osiris reads their workouts. */
class HealthRationaleActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            OsirisTheme {
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.safeDrawingPadding().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        Text("How Osiris uses Health Connect", style = MaterialTheme.typography.headlineSmall)
                        Text(
                            "When you tap Import on your Progress page, Osiris reads the workouts from the last 30 " +
                                "days, with their heart rate, speed, power and distance, and saves them to your " +
                                "activity history. Nothing is read in the background and Osiris never writes to " +
                                "Health Connect. Workouts stay private unless you post them.",
                        )
                        val links = LocalUriHandler.current
                        val baseUrl = (application as OsirisApplication).graph.config.apiBaseUrl
                        TextButton(onClick = { links.openUri("$baseUrl/privacy") }) { Text("Privacy policy") }
                        TextButton(onClick = ::finish) { Text("Close") }
                    }
                }
            }
        }
    }
}
