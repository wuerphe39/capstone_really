from petmind.backend.providers import gemini_output_schema


def test_single_allowed_action_uses_supported_enum_not_const():
    schema = gemini_output_schema()
    item = schema['properties']['recommended_actions']['items']
    assert item['enum'] == ['music']
    assert 'const' not in item
    assert schema['properties']['recommended_actions']['maxItems'] == 1
