package com.osiris.shared.data.support

import com.osiris.shared.core.error.AppError
import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.data.network.NetworkErrors
import com.osiris.shared.domain.model.SupportMessage
import com.osiris.shared.domain.model.SupportOutgoing
import com.osiris.shared.domain.repository.SupportChatRepository
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.launch
import kotlinx.io.IOException
import kotlinx.serialization.SerializationException

class SupportChatRepositoryImpl(private val api: ApiClient) : SupportChatRepository {
    override fun open(outgoing: ReceiveChannel<String>): Flow<SupportMessage> = channelFlow {
        api.webSocket(PATH) {
            val writer = launch {
                for (text in outgoing) {
                    send(Frame.Text(api.json.encodeToString(SupportOutgoing.serializer(), SupportOutgoing(text))))
                }
            }
            try {
                for (frame in incoming) {
                    if (frame !is Frame.Text) continue
                    val message = try {
                        api.json.decodeFromString(SupportMessage.serializer(), frame.readText())
                    } catch (e: SerializationException) {
                        throw AppError.InvalidResponse(e)
                    }
                    this@channelFlow.send(message)
                }
            } catch (e: IOException) {
                // The connection dropped mid-chat.
                throw NetworkErrors.fromThrowable(e)
            } finally {
                writer.cancel()
            }
        }
    }

    private companion object {
        const val PATH = "/api/v2/support/ws"
    }
}
