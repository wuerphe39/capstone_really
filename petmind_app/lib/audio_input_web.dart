import 'dart:js_interop';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

Widget audioInput(void Function(String, Uint8List) onSelected, void Function(String) onError) =>
  SizedBox(height: 42, child: HtmlElementView.fromTagName(tagName: 'input', onElementCreated: (element) {
    final input = element as web.HTMLInputElement;
    input.type = 'file'; input.accept = '.wav,audio/wav';
    input.setAttribute('aria-label', '분석할 WAV 파일 선택');
    input.style.color = '#0A0A0A';
    input.onchange = ((web.Event event) {
      final file = input.files?.item(0);
      if (file == null) return;
      if (file.size > 12*1024*1024) { onError('파일은 12MB 이하여야 합니다.'); return; }
      file.arrayBuffer().toDart.then((value) => onSelected(file.name, value.toDart.asUint8List()))
        .catchError((Object error) { onError('파일을 읽지 못했습니다.'); });
    }).toJS;
  }));
