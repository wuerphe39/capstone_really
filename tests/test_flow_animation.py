import importlib.util
import re
import unittest
import xml.dom.minidom
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("build_flow_animation", Path(__file__).resolve().parents[1] / "scripts" / "build_flow_animation.py")
flow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flow)


class FlowAnimationTests(unittest.TestCase):
    def test_steps_reference_existing_nodes_and_edges(self):
        for s in flow.STEPS:
            for n in s["nodes"]:
                self.assertIn(n, flow.NODES)
            for eid, rev in s["packets"]:
                self.assertIn(eid, flow.EDGES)
                self.assertIsInstance(rev, bool)

    def test_every_node_and_edge_is_used(self):
        used_nodes = set().union(*flow.STEP_NODES)
        used_edges = {p[0] for s in flow.STEPS for p in s["packets"]}
        self.assertEqual(used_nodes, set(flow.NODES))
        # 카메라·마이크→에이전트 등 모든 간선이 한 번은 강조되어야 한다
        self.assertEqual(used_edges, set(flow.EDGES))

    def test_svg_is_valid_xml_with_monotonic_keytimes(self):
        svg = flow.build_svg()
        xml.dom.minidom.parseString(svg)
        for kt in re.findall(r'keyTimes="([^"]+)"', svg):
            xs = [float(v) for v in kt.split(";")]
            self.assertEqual(xs[0], 0.0)
            self.assertEqual(xs[-1], 1.0)
            self.assertTrue(all(b > a for a, b in zip(xs, xs[1:])), kt)

    def test_values_and_keytimes_have_equal_length(self):
        svg = flow.build_svg()
        for m in re.finditer(r'<animate [^>]*values="([^"]+)"[^>]*keyTimes="([^"]+)"', svg):
            self.assertEqual(len(m.group(1).split(";")), len(m.group(2).split(";")))

    def test_html_contains_all_steps_and_no_external_resources(self):
        page = flow.build_html()
        for s in flow.STEPS:
            self.assertIn(s["title"], page)
        self.assertNotRegex(page, r'(src|href)="https?://')


if __name__ == "__main__":
    unittest.main()
