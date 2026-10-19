package com.osiris.player.ui.theme

import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** The Osiris dark palette, the same values as the Flutter theme. */
object OsirisColors {
    val Background = Color(0xFF121212)
    val Surface = Color(0xFF1E1E1E)
    val Primary = Color(0xFF9D4EDD)
    val Secondary = Color(0xFF03DAC6)
    val Error = Color(0xFFCF6679)
    val Success = Color(0xFF4CAF50)
    val Warning = Color(0xFFFFC107)
    val Gold = Color(0xFFFDD835)
    val Muted = Color(0xB3FFFFFF)
    val Faint = Color(0x99FFFFFF)
}

private val scheme = darkColorScheme(
    primary = OsirisColors.Primary,
    onPrimary = Color.White,
    secondary = OsirisColors.Secondary,
    onSecondary = Color.Black,
    background = OsirisColors.Background,
    onBackground = Color.White,
    surface = OsirisColors.Surface,
    onSurface = Color.White,
    surfaceContainer = OsirisColors.Surface,
    error = OsirisColors.Error,
    onError = Color.Black,
)

private val type = Typography(
    headlineMedium = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = 2.sp),
    headlineSmall = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 16.sp),
    bodyMedium = TextStyle(fontSize = 14.sp),
    labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp),
)

@Composable
fun OsirisTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, typography = type, content = content)
}

@Composable
fun primaryButtonColors() = ButtonDefaults.buttonColors(containerColor = OsirisColors.Primary, contentColor = Color.White)
