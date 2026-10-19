package com.osiris.player.ui.common

import androidx.compose.runtime.Composable
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import com.osiris.shared.presentation.common.SharedViewModel

/** Keeps a shared view model alive across configuration changes and clears it with the screen. */
class SharedViewModelHolder<VM : SharedViewModel>(val vm: VM) : ViewModel() {
    override fun onCleared() = vm.clear()
}

/**
 * The shared view model for the current navigation entry. [key] distinguishes two instances of
 * one screen type in the same entry (rarely needed: each destination is its own store owner).
 */
@Composable
inline fun <reified VM : SharedViewModel> rememberShared(key: String? = null, noinline create: () -> VM): VM {
    val holder = viewModel<SharedViewModelHolder<VM>>(key = key ?: VM::class.java.name) { SharedViewModelHolder(create()) }
    return holder.vm
}
