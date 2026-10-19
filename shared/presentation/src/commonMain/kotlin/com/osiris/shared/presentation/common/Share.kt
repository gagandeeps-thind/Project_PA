package com.osiris.shared.presentation.common

/**
 * Text the screen should hand to the platform share sheet (or copy to the clipboard). The
 * screen calls back once it is shared, so the `share_completed` event is recorded.
 */
data class ShareRequest(val text: String, val kind: String)
