import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:google_mlkit_pose_detection/google_mlkit_pose_detection.dart';

import 'pose_frame.dart';
import 'pose_source.dart';

/// Camera + ML Kit BlazePose, entirely on device.
///
/// Performance choices: a medium-resolution stream (pose landmarks need ~480p, not 4K), the
/// fast `base` model in stream mode (it tracks between frames), no audio, and at most one
/// frame in flight: frames that arrive while ML Kit is busy are dropped, never queued, so
/// latency stays one frame deep however slow the phone is.
class MlKitPoseSource extends PoseSource {
  final bool useFrontCamera;

  MlKitPoseSource({this.useFrontCamera = true});

  static const _landmarkNames = <PoseLandmarkType, String>{
    PoseLandmarkType.nose: 'nose',
    PoseLandmarkType.leftShoulder: 'left_shoulder',
    PoseLandmarkType.rightShoulder: 'right_shoulder',
    PoseLandmarkType.leftElbow: 'left_elbow',
    PoseLandmarkType.rightElbow: 'right_elbow',
    PoseLandmarkType.leftWrist: 'left_wrist',
    PoseLandmarkType.rightWrist: 'right_wrist',
    PoseLandmarkType.leftHip: 'left_hip',
    PoseLandmarkType.rightHip: 'right_hip',
    PoseLandmarkType.leftKnee: 'left_knee',
    PoseLandmarkType.rightKnee: 'right_knee',
    PoseLandmarkType.leftAnkle: 'left_ankle',
    PoseLandmarkType.rightAnkle: 'right_ankle',
  };

  static const _orientationDegrees = {
    DeviceOrientation.portraitUp: 0,
    DeviceOrientation.landscapeLeft: 90,
    DeviceOrientation.portraitDown: 180,
    DeviceOrientation.landscapeRight: 270,
  };

  final _controller = StreamController<PoseFrame>.broadcast();
  final _detector = PoseDetector(
    options: PoseDetectorOptions(mode: PoseDetectionMode.stream, model: PoseDetectionModel.base),
  );
  CameraController? _camera;
  bool _busy = false;
  final _clock = Stopwatch();
  Size? _imageSize;
  bool _mirrored = false;

  @override
  Stream<PoseFrame> get frames => _controller.stream;

  @override
  Size? get imageSize => _imageSize;

  @override
  bool get mirrored => _mirrored;

  @override
  Future<void> start() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) throw CameraException('NoCamera', 'This device has no camera');
    final wanted = useFrontCamera ? CameraLensDirection.front : CameraLensDirection.back;
    final description = cameras.firstWhere((c) => c.lensDirection == wanted, orElse: () => cameras.first);
    _mirrored = description.lensDirection == CameraLensDirection.front;
    final camera = CameraController(
      description,
      ResolutionPreset.medium,
      enableAudio: false,
      fps: 30,
      imageFormatGroup: Platform.isAndroid ? ImageFormatGroup.nv21 : ImageFormatGroup.bgra8888,
    );
    _camera = camera;
    await camera.initialize();
    _clock.start();
    await camera.startImageStream(_onImage);
  }

  Future<void> _onImage(CameraImage image) async {
    if (_busy) {
      stats.dropped++;
      return;
    }
    final camera = _camera;
    final input = camera == null ? null : _toInputImage(image, camera);
    if (input == null) return;
    _busy = true;
    final tMs = _clock.elapsedMilliseconds;
    final t0 = _clock.elapsedMicroseconds;
    try {
      final poses = await _detector.processImage(input);
      stats.record(tMs, _clock.elapsedMicroseconds - t0);
      final rotated = input.metadata!.rotation == InputImageRotation.rotation90deg ||
          input.metadata!.rotation == InputImageRotation.rotation270deg;
      _imageSize = rotated ? Size(image.height.toDouble(), image.width.toDouble()) : input.metadata!.size;
      final landmarks = <String, Landmark>{};
      if (poses.isNotEmpty) {
        for (final e in poses.first.landmarks.entries) {
          final name = _landmarkNames[e.key];
          if (name != null) landmarks[name] = Landmark(e.value.x, e.value.y, e.value.likelihood);
        }
      }
      if (!_controller.isClosed) _controller.add(PoseFrame(tMs, landmarks));
    } on PlatformException {
      stats.dropped++;
    } finally {
      _busy = false;
    }
  }

  InputImage? _toInputImage(CameraImage image, CameraController camera) {
    final sensor = camera.description.sensorOrientation;
    InputImageRotation? rotation;
    if (Platform.isIOS) {
      rotation = InputImageRotationValue.fromRawValue(sensor);
    } else {
      final device = _orientationDegrees[camera.value.deviceOrientation] ?? 0;
      final compensation = camera.description.lensDirection == CameraLensDirection.front
          ? (sensor + device) % 360
          : (sensor - device + 360) % 360;
      rotation = InputImageRotationValue.fromRawValue(compensation);
    }
    final format = InputImageFormatValue.fromRawValue(image.format.raw as int);
    if (rotation == null || format == null || image.planes.length != 1) return null;
    final plane = image.planes.first;
    return InputImage.fromBytes(
      bytes: plane.bytes,
      metadata: InputImageMetadata(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        rotation: rotation,
        format: format,
        bytesPerRow: plane.bytesPerRow,
      ),
    );
  }

  @override
  Future<void> stop() async {
    final camera = _camera;
    _camera = null;
    if (camera != null) {
      if (camera.value.isStreamingImages) await camera.stopImageStream();
      await camera.dispose();
    }
    await _detector.close();
    await _controller.close();
  }

  @override
  Widget? buildPreview() {
    final camera = _camera;
    if (camera == null || !camera.value.isInitialized) return null;
    return CameraPreview(camera);
  }
}
