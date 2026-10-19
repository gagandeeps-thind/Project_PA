package com.osiris.shared.data

import com.osiris.shared.data.network.api.ChallengeApi
import com.osiris.shared.domain.model.AttemptSummary
import com.osiris.shared.domain.model.BlockEntry
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.Community
import com.osiris.shared.domain.model.ConsentState
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.model.CourseSummary
import com.osiris.shared.domain.model.ExerciseHistoryResponse
import com.osiris.shared.domain.model.ExerciseUpload
import com.osiris.shared.domain.model.ExerciseUploadResult
import com.osiris.shared.domain.model.GlobalBoard
import com.osiris.shared.domain.model.HubSectionData
import com.osiris.shared.domain.model.InviteLink
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.model.LoginResponse
import com.osiris.shared.domain.model.MessageResponse
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.model.ReferralSummary
import com.osiris.shared.domain.model.RegisterResponse
import com.osiris.shared.domain.model.RoutePoint
import com.osiris.shared.domain.model.RunRecord
import com.osiris.shared.domain.model.RunResult
import com.osiris.shared.domain.model.Season
import com.osiris.shared.domain.model.SeasonLeaderboard
import com.osiris.shared.domain.model.ShareCard
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.model.TokenResponse
import com.osiris.shared.domain.model.UserProfile
import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.fail
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.descriptors.StructureKind
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Checks the shared code against the committed backend contract (Documentation/openapi.json, kept
 * current by the backend's drift check), so a renamed field or a wrong response shape fails here
 * instead of on a phone.
 *
 * For every response model: each Kotlin field must exist on the server schema, and each Kotlin
 * field without a default must be one the server always sends. Request bodies are checked the
 * other way round: every field the server requires must be sent.
 */
class ContractTest {
    private val spec = Json.parseToJsonElement(File(System.getProperty("osiris.openapi")).readText()).jsonObject
    private val schemas = spec["components"]!!.jsonObject["schemas"]!!.jsonObject

    private val responses: List<Triple<String, String, KSerializer<*>>> = listOf(
        Triple("POST", "/api/v1/auth/login", LoginResponse.serializer()),
        Triple("GET", "/api/v1/users/{}", UserProfile.serializer()),
        Triple("POST", "/api/v2/auth/register", RegisterResponse.serializer()),
        Triple("POST", "/api/v2/me/sessions/revoke", TokenResponse.serializer()),
        Triple("POST", "/api/v2/runs", RunRecord.serializer()),
        Triple("GET", "/api/v2/runs/{}", RunRecord.serializer()),
        Triple("POST", "/api/v2/runs/{}/finish", RunResult.serializer()),
        Triple("GET", "/api/v2/challenges/nearby", ListSerializer(ChallengeSummary.serializer())),
        Triple("GET", "/api/v2/challenges/{}", ChallengeSummary.serializer()),
        Triple("GET", "/api/v2/challenges/{}/course", CourseRoute.serializer()),
        Triple("POST", "/api/v2/challenges/{}/attempts", AttemptSummary.serializer()),
        Triple("POST", "/api/v2/challenges", ChallengeApi.Created.serializer()),
        Triple("POST", "/api/v2/challenges/{}/invites", InviteLink.serializer()),
        Triple("GET", "/api/v2/courses", ListSerializer(CourseSummary.serializer())),
        Triple("POST", "/api/v2/reports", MessageResponse.serializer()),
        Triple("GET", "/api/v2/me/today", TodayData.serializer()),
        Triple("GET", "/api/v2/me/profile", PlayerProfile.serializer()),
        Triple("PUT", "/api/v2/me/profile", PlayerProfile.serializer()),
        Triple("GET", "/api/v2/me/progression", Progression.serializer()),
        Triple("GET", "/api/v2/me/referrals", ReferralSummary.serializer()),
        Triple("POST", "/api/v2/share", ShareCard.serializer()),
        Triple("GET", "/api/v2/me/blocks", ListSerializer(BlockEntry.serializer())),
        Triple("GET", "/api/v2/communities", ListSerializer(Community.serializer())),
        Triple("GET", "/api/v2/me/communities", ListSerializer(Community.serializer())),
        Triple("GET", "/api/v2/communities/{}", Community.serializer()),
        Triple("POST", "/api/v2/communities/{}/join", Community.serializer()),
        Triple("GET", "/api/v2/communities/{}/leaderboard", Leaderboard.serializer()),
        Triple("GET", "/api/v2/communities/{}/challenges", ListSerializer(ChallengeSummary.serializer())),
        Triple("GET", "/api/v2/leaderboards/local", Leaderboard.serializer()),
        Triple("GET", "/api/v2/seasons", ListSerializer(Season.serializer())),
        Triple("GET", "/api/v2/seasons/{}/leaderboard", SeasonLeaderboard.serializer()),
        Triple("GET", "/api/v2/challenge-hub", HubSectionData.serializer()),
        Triple("GET", "/api/v2/leaderboards/global", GlobalBoard.serializer()),
        Triple("POST", "/api/v2/exercise-sessions", ExerciseUploadResult.serializer()),
        Triple("GET", "/api/v2/me/exercise-consent", ConsentState.serializer()),
        Triple("PUT", "/api/v2/me/exercise-consent", ConsentState.serializer()),
        Triple("GET", "/api/v2/me/exercise-sessions", ExerciseHistoryResponse.serializer()),
    )

    private val requests: List<Triple<String, String, KSerializer<*>>> = listOf(
        Triple("POST", "/api/v2/exercise-sessions", ExerciseUpload.serializer()),
        Triple("POST", "/api/v2/runs/{}/points", RoutePointsBody.serializer()),
    )

    @kotlinx.serialization.Serializable
    private data class RoutePointsBody(val points: List<RoutePoint>)

    @Test
    fun `every endpoint the app calls exists in the contract`() {
        val known = spec["paths"]!!.jsonObject.flatMap { (path, ops) -> ops.jsonObject.keys.map { "${it.uppercase()} ${normalize(path)}" } }.toSet()
        val used = apiSourceCalls()
        assertTrue(used.size > 40, "found only ${used.size} calls; is the source scan broken?")
        val missing = used - known
        assertTrue(missing.isEmpty(), "Endpoints not in openapi.json: $missing")
    }

    @Test
    fun `response models match the server schemas`() {
        val problems = responses.flatMap { (method, path, serializer) ->
            val schema = responseSchema(method, path) ?: return@flatMap listOf("$method $path: no response schema")
            compare(serializer.descriptor, schema, "$method $path", request = false)
        }
        if (problems.isNotEmpty()) fail(problems.joinToString("\n"))
    }

    @Test
    fun `request bodies send every field the server requires`() {
        val problems = requests.flatMap { (method, path, serializer) ->
            compare(serializer.descriptor, requestSchema(method, path), "$method $path body", request = true)
        }
        if (problems.isNotEmpty()) fail(problems.joinToString("\n"))
    }

    private fun compare(d: SerialDescriptor, rawSchema: JsonObject, at: String, request: Boolean): List<String> {
        val schema = resolve(rawSchema)
        return when (d.kind) {
            StructureKind.LIST -> schema["items"]?.let { compare(d.getElementDescriptor(0), it.jsonObject, "$at[]", request) }
                ?: listOf("$at: server sends ${schema["type"]}, app expects a list")
            StructureKind.CLASS -> {
                val props = schema["properties"]?.jsonObject ?: return listOf("$at: server sends no object")
                val required = schema["required"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty().toSet()
                (0 until d.elementsCount).flatMap { i ->
                    val name = d.getElementName(i)
                    val prop = props[name]?.jsonObject
                    when {
                        prop == null && request -> listOf("$at.$name: the server does not accept this field")
                        prop == null -> listOf("$at.$name: the server never sends this field")
                        !request && !d.isElementOptional(i) && name !in required ->
                            listOf("$at.$name: the server may omit it; give it a default")
                        else -> compare(d.getElementDescriptor(i), prop, "$at.$name", request)
                    }
                } + if (request) (required - (0 until d.elementsCount).map { d.getElementName(it) }.toSet()).map {
                    "$at.$it: required by the server, never sent"
                } else emptyList()
            }
            else -> emptyList() // primitives, enums, maps and custom serializers (instants, routes)
        }.let { if (d.kind is PrimitiveKind) emptyList() else it }
    }

    /** Follows `$ref` and unwraps `anyOf: [X, null]` (Optional fields). */
    private fun resolve(s: JsonObject): JsonObject {
        s["\$ref"]?.let { return resolve(schemas[it.jsonPrimitive.content.substringAfterLast('/')]!!.jsonObject) }
        val anyOf = s["anyOf"] as? JsonArray
        if (anyOf != null) {
            val real = anyOf.map { it.jsonObject }.filter { it["type"]?.jsonPrimitive?.content != "null" }
            if (real.size == 1) return resolve(real.single())
        }
        return s
    }

    private fun operation(method: String, path: String): JsonObject {
        val (_, ops) = spec["paths"]!!.jsonObject.entries.firstOrNull { normalize(it.key) == path }
            ?: error("$path is not in openapi.json")
        return ops.jsonObject[method.lowercase()]?.jsonObject ?: error("$method $path is not in openapi.json")
    }

    private fun responseSchema(method: String, path: String): JsonObject? {
        val responses = operation(method, path)["responses"]!!.jsonObject
        return listOf("200", "201").firstNotNullOfOrNull { code ->
            responses[code]?.jsonObject?.get("content")?.jsonObject?.get("application/json")?.jsonObject?.get("schema")?.jsonObject
                ?.takeIf { it.isNotEmpty() }
        }
    }

    private fun requestSchema(method: String, path: String): JsonObject =
        operation(method, path)["requestBody"]!!.jsonObject["content"]!!.jsonObject["application/json"]!!.jsonObject["schema"]!!.jsonObject

    private fun normalize(path: String) = path.replace(Regex("\\{[^}]+}"), "{}")

    /** Every `METHOD /path` in the API service sources, with interpolations as `{}`. */
    private fun apiSourceCalls(): Set<String> {
        val dir = File(System.getProperty("osiris.openapi")).parentFile.parentFile
            .resolve("shared/data/src/commonMain/kotlin/com/osiris/shared/data/network/api")
        val call = Regex("""api\.(get|post|put|postBody)\s*(?:<[^>]*>)?\(\s*"([^"]+)"|execute\(\s*HttpMethod\.(\w+),\s*"([^"]+)"""")
        return dir.listFiles()!!.flatMap { file ->
            call.findAll(file.readText()).map { m ->
                val method = (m.groups[1]?.value?.let { if (it == "postBody") "post" else it } ?: m.groups[3]!!.value).uppercase()
                val path = (m.groups[2] ?: m.groups[4])!!.value.replace(Regex("""\$\{[^}]+}|\$\w+"""), "{}")
                "$method $path"
            }.toList()
        }.toSet()
    }

    @Suppress("unused")
    private fun JsonElement.debug() = toString()
}
