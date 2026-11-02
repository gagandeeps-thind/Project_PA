package com.osiris.player.platform.ble

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.ParcelUuid
import com.osiris.player.platform.permission.granted
import com.osiris.shared.domain.training.BleParsers
import com.osiris.shared.domain.training.Channel
import java.util.UUID
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/** A sensor seen while scanning, with the channels its services provide. */
data class FoundSensor(val address: String, val name: String, val channels: Set<Channel>)

/**
 * Bluetooth LE fitness sensors: heart-rate straps and watches in HR broadcast mode, power meters,
 * running pods and bike speed sensors, through the standard Bluetooth SIG profiles.
 */
class BleSensors(context: Context) {
    private val app = context.applicationContext
    private val adapter get() = app.getSystemService(BluetoothManager::class.java)?.adapter

    val available: Boolean get() = adapter != null
    val enabled: Boolean get() = adapter?.isEnabled == true

    /** Runtime permissions for scanning and connecting on this Android version. */
    val permissions: Array<String> = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    } else {
        arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }

    fun hasPermission(): Boolean = permissions.all(app::granted)

    /** Sensors in range, growing as more are found. Stops scanning when collection stops. */
    @SuppressLint("MissingPermission")
    fun scan(): Flow<List<FoundSensor>> = callbackFlow {
        val scanner = adapter?.bluetoothLeScanner
        if (scanner == null || !hasPermission()) {
            trySend(emptyList())
            close()
            return@callbackFlow
        }
        val found = linkedMapOf<String, FoundSensor>()
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val uuids = result.scanRecord?.serviceUuids.orEmpty().map { it.uuid.toString() }
                val channels = uuids.mapNotNull(BleParsers.services::get).toSet()
                if (channels.isEmpty()) return
                val name = result.scanRecord?.deviceName ?: result.device.name
                    ?: "Sensor ${result.device.address.takeLast(ADDRESS_TAIL)}"
                found[result.device.address] = FoundSensor(result.device.address, name, channels)
                trySend(found.values.toList())
            }
        }
        val filters = BleParsers.services.keys.map { ScanFilter.Builder().setServiceUuid(ParcelUuid.fromString(it)).build() }
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        trySend(emptyList())
        scanner.startScan(filters, settings, callback)
        awaitClose { runCatching { scanner.stopScan(callback) } }
    }

    /**
     * Live readings from the sensor at [address]. Notifications are turned on for every supported
     * measurement it offers; a dropped link reconnects by itself. Disconnects when collection stops.
     */
    @SuppressLint("MissingPermission")
    fun connect(address: String): Flow<Pair<Channel, Double>> = callbackFlow {
        val device: BluetoothDevice? = runCatching { adapter?.getRemoteDevice(address) }.getOrNull()
        if (device == null || !hasPermission()) {
            close()
            return@callbackFlow
        }
        val csc = BleParsers.CscSpeed()
        val pending = ArrayDeque<BluetoothGattDescriptor>()
        var closed = false

        fun emit(uuid: String, bytes: ByteArray) {
            reading(uuid, bytes, csc)?.let { trySend(it) }
        }

        fun writeNext(gatt: BluetoothGatt) {
            pending.removeFirstOrNull()?.let { gatt.enableNotifications(it) }
        }

        val callback = object : BluetoothGattCallback() {
            override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
                when (newState) {
                    BluetoothProfile.STATE_CONNECTED -> gatt.discoverServices()
                    BluetoothProfile.STATE_DISCONNECTED -> if (!closed) gatt.connect()
                }
            }

            override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
                pending.clear()
                pending.addAll(gatt.measurementDescriptors())
                // GATT runs one write at a time; the next goes out when this one lands.
                writeNext(gatt)
            }

            override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) =
                writeNext(gatt)

            override fun onCharacteristicChanged(gatt: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray) =
                emit(c.uuid.toString(), value)

            @Suppress("OVERRIDE_DEPRECATION") // Android 12 and older deliver the value on the characteristic
            override fun onCharacteristicChanged(gatt: BluetoothGatt, c: BluetoothGattCharacteristic) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
                    @Suppress("DEPRECATION")
                    emit(c.uuid.toString(), c.value ?: return)
                }
            }
        }
        val gatt = device.connectGatt(app, false, callback, BluetoothDevice.TRANSPORT_LE)
        awaitClose {
            closed = true
            runCatching {
                gatt.disconnect()
                gatt.close()
            }
        }
    }
}

private const val ADDRESS_TAIL = 5

/** One measurement packet as a reading, or null if it does not decode. */
private fun reading(uuid: String, bytes: ByteArray, csc: BleParsers.CscSpeed): Pair<Channel, Double>? = when (uuid) {
    BleParsers.HR_MEASUREMENT -> BleParsers.heartRate(bytes)?.let { Channel.HR to it.toDouble() }
    BleParsers.CP_MEASUREMENT -> BleParsers.cyclingPower(bytes)?.let { Channel.POWER to it.toDouble() }
    BleParsers.RSC_MEASUREMENT -> BleParsers.rscSpeedMps(bytes)?.let { Channel.SPEED to it }
    BleParsers.CSC_MEASUREMENT -> csc.next(bytes)?.let { Channel.SPEED to it }
    else -> null
}

/** Turns notifications on for every supported measurement; returns the descriptors still to write. */
@SuppressLint("MissingPermission")
private fun BluetoothGatt.measurementDescriptors(): List<BluetoothGattDescriptor> =
    BleParsers.measurements.mapNotNull { (service, measurement) ->
        getService(UUID.fromString(service))?.getCharacteristic(UUID.fromString(measurement))?.let { c ->
            setCharacteristicNotification(c, true)
            c.getDescriptor(UUID.fromString(BleParsers.NOTIFY_DESCRIPTOR))
        }
    }

@SuppressLint("MissingPermission")
private fun BluetoothGatt.enableNotifications(descriptor: BluetoothGattDescriptor) {
    val on = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        writeDescriptor(descriptor, on)
    } else {
        @Suppress("DEPRECATION")
        descriptor.value = on
        @Suppress("DEPRECATION")
        writeDescriptor(descriptor)
    }
}
