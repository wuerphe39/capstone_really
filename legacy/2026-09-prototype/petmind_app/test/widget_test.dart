import 'package:flutter_test/flutter_test.dart';
import 'package:petmind_app/main.dart';

void main() {
  testWidgets('shows the care dashboard', (tester) async {
    await tester.pumpWidget(const PetMindApp());
    expect(find.text('PetMind Care'), findsOneWidget);
    expect(find.text('현재 상태 평가하기'), findsOneWidget);
  });
}
