import 'dart:typed_data';
import 'package:flutter/material.dart';

Widget audioInput(void Function(String, Uint8List) onSelected, void Function(String) onError) =>
    const Text('WAV 업로드는 웹 화면에서 지원합니다.');
