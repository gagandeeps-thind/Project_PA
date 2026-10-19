# Pose recordings (device QA)

Each `*.json` file here is one exercise set's pose stream, labeled by the person who did it.
`recordings_replay_test.dart` replays every file through the rep engine and checks the count
against the label, so a recording added after a device QA session stays a regression case.

## Recording on a phone

1. Run a **debug** build (`flutter run`), or a profile build with
   `--dart-define=OSIRIS_POSE_RECORDING=true`. Release builds cannot record.
2. Open Bodyweight, pick the exercise, and tap the record icon (top right) before START.
3. Do the set. After FINISH, enter the number of reps that *should* count (seconds of good hold
   for plank). Deliberately bad sets are useful too: half reps are labeled 0.
4. The file is saved on the phone; the snackbar shows its path.

## Copying a recording off the phone

- Android: `adb exec-out run-as com.example.osiris_customer ls databases/pose_recordings`, then
  `adb exec-out run-as com.example.osiris_customer cat databases/pose_recordings/<file>.json > <file>.json`
- iOS: Xcode > Window > Devices and Simulators > Osiris > Download Container, then
  `AppData/Documents/pose_recordings/` (sqflite's databases folder).

## Format `osiris-pose-v1`

```json
{
  "format": "osiris-pose-v1",
  "exercise_key": "pushup",
  "rules_version": "exercise-rules-v2",
  "recorded_at": "2026-10-17T10:00:00.000Z",
  "source": "device",
  "label_reps": 12,
  "label_hold_s": null,
  "note": null,
  "frames": [{"t": 0, "l": {"left_elbow": [212.4, 301.0, 0.97], "...": []}}]
}
```

`t` is milliseconds on the phone's monotonic clock; each landmark is `[x, y, likelihood]` in image
pixels (rotated upright), x and y to 0.1 px. No images are ever stored.

## Governance

Recordings are movement data of a real person. Record only testers who agreed to it, keep the
`note` free of names, and commit a recording only with that person's consent. `source:
synthetic` files are generated, not recorded.
