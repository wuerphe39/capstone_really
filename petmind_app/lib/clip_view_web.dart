import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

Widget clipView(String url) => Column(children: [
  const Text('팝업 안에서 재생 버튼이 반응하지 않으면 새 탭에서 원본을 확인하세요.'),
  OutlinedButton.icon(
    onPressed: () { web.window.open(url, '_blank', 'noopener'); },
    icon: const Icon(Icons.open_in_new),
    label: const Text('원본 플레이어 새 탭에서 열기'),
  ),
  Expanded(child: HtmlElementView.fromTagName(
  tagName: 'iframe',
  onElementCreated: (element) {
    final frame = element as web.HTMLIFrameElement;
    frame.src = url;
    frame.title = '관찰 근거 영상 구간';
    frame.style.width = '100%';
    frame.style.height = '100%';
    frame.style.border = '0';
  },
  )),
]);
