"""Small BPMN / DMN / form writer for the E2E seed catalog (M8F-677).

Diagrams are described on a grid: a node sits in a column, a lane and a row
inside that lane; the writer works out the shapes, edges and lanes. Only the
standard library is used, so it runs with any Python 3.10+.

    d = Diagram("e2e_travel_request", "Travel Request", lanes=[("Submitters", 2), ("Approvers", 1)])
    d.start("start", "Trip needed", 0, "Submitters")
    d.user("submit", "Submit request", 1, "Submitters", form="trip-request")
    d.flow("start", "submit")
    xml = d.to_xml()
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


# Text and attribute escaping for the XML we write (same output as xml.sax.saxutils).
# Written out here so this generator imports no XML parser package at all.
def escape(data: str) -> str:
    return data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def quoteattr(data: str) -> str:
    data = escape(data).replace("\n", "&#10;").replace("\r", "&#13;").replace("\t", "&#9;")
    if '"' in data:
        return '"%s"' % data.replace('"', "&quot;") if "'" in data else "'%s'" % data
    return '"%s"' % data


X0, COLW, RH, LANE_X, POOL_X = 230, 165, 150, 160, 130
SIZES = {"event": (36, 36), "gateway": (50, 50), "task": (100, 80), "data": (36, 50)}
EVENT_TAGS = {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent", "boundaryEvent"}
GATEWAY_TAGS = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway"}
CONTAINER_TAGS = {"subProcess", "transaction"}


def py(value: str) -> str:
    """A Python string literal, for expressions such as timer durations."""
    return repr(value).replace("'", '"')


def x(text: str) -> str:
    return escape(text)


def ext(*, form: str | None = None, ui: bool = True, instructions: str | None = None,
        pre: str | None = None, post: str | None = None, extra: str = "") -> str:
    parts: list[str] = []
    if form:
        props = f'<spiffworkflow:property name="formJsonSchemaFilename" value="{form}-schema.json" />'
        if ui:
            props += f'<spiffworkflow:property name="formUiSchemaFilename" value="{form}-uischema.json" />'
        parts.append(f"<spiffworkflow:properties>{props}</spiffworkflow:properties>")
    if instructions:
        parts.append(f"<spiffworkflow:instructionsForEndUser>{x(instructions)}</spiffworkflow:instructionsForEndUser>")
    if extra:
        parts.append(extra)
    if pre:
        parts.append(f"<spiffworkflow:preScript>{x(pre)}</spiffworkflow:preScript>")
    if post:
        parts.append(f"<spiffworkflow:postScript>{x(post)}</spiffworkflow:postScript>")
    return f"<bpmn:extensionElements>{''.join(parts)}</bpmn:extensionElements>" if parts else ""


@dataclass
class Node:
    id: str
    tag: str
    name: str | None
    col: float
    lane: str
    row: float
    parent: str | None = None
    attrs: str = ""
    ext: str = ""
    body: str = ""
    kind: str = "task"
    bounds: tuple[float, float, float, float] = (0, 0, 0, 0)


@dataclass
class Flow:
    id: str
    source: str
    target: str
    name: str | None = None
    condition: str | None = None
    over: bool = False  # draw above the row, e.g. to pass over the tasks of another branch


@dataclass
class Diagram:
    process_id: str
    name: str
    lanes: list[tuple[str, int]]
    documentation: str = ""
    nodes: dict[str, Node] = field(default_factory=dict)
    flows: list[Flow] = field(default_factory=list)
    defaults: dict[str, str] = field(default_factory=dict)
    root_xml: list[str] = field(default_factory=list)  # signals, errors, escalations, messages, categories
    process_xml: list[str] = field(default_factory=list)  # data objects, io specification, annotations
    partner: tuple[str, str] | None = None  # (participant id, name)
    message_flows: list[tuple[str, str, str, str, str | None]] = field(default_factory=list)
    annotations: list[tuple[str, str, str, float, str, float]] = field(default_factory=list)
    associations: list[tuple[str, str, str]] = field(default_factory=list)  # data associations to draw
    groups: list[tuple[str, str, list[str]]] = field(default_factory=list)
    io_spec: str = ""

    # ---- nodes ------------------------------------------------------------------
    def _add(self, nid: str, tag: str, name: str | None, col: float, lane: str, row: float = 0, **kw) -> Node:
        assert nid not in self.nodes, nid
        assert lane in dict(self.lanes), lane
        kind = "event" if tag in EVENT_TAGS else "gateway" if tag in GATEWAY_TAGS else "container" if tag in CONTAINER_TAGS else "data" if tag == "dataObjectReference" else "task"
        node = Node(nid, tag, name, col, lane, row, kind=kind, **kw)
        self.nodes[nid] = node
        return node

    def start(self, nid, name, col, lane, row=0, **kw):
        return self._add(nid, "startEvent", name, col, lane, row, **kw)

    def end(self, nid, name, col, lane, row=0, definition: str = "", **kw):
        return self._add(nid, "endEvent", name, col, lane, row, body=definition, **kw)

    def user(self, nid, name, col, lane, row=0, *, form=None, ui=True, instructions=None, pre=None, post=None, body="", **kw):
        return self._add(nid, "userTask", name, col, lane, row,
                         ext=ext(form=form, ui=ui, instructions=instructions, pre=pre, post=post), body=body, **kw)

    def manual(self, nid, name, col, lane, row=0, *, instructions=None, **kw):
        return self._add(nid, "manualTask", name, col, lane, row, ext=ext(instructions=instructions), **kw)

    def task(self, nid, name, col, lane, row=0, *, instructions=None, **kw):
        return self._add(nid, "task", name, col, lane, row, ext=ext(instructions=instructions), **kw)

    def script(self, nid, name, col, lane, row=0, *, code: str, loop: str = "", assoc: str = "", **kw):
        return self._add(nid, "scriptTask", name, col, lane, row, attrs=' scriptFormat="python"',
                         body=f"{assoc}{loop}<bpmn:script>{x(code)}</bpmn:script>", **kw)

    def rule(self, nid, name, col, lane, row=0, *, decision: str, post=None, **kw):
        return self._add(nid, "businessRuleTask", name, col, lane, row,
                         ext=ext(extra=f"<spiffworkflow:calledDecisionId>{decision}</spiffworkflow:calledDecisionId>", post=post), **kw)

    def service(self, nid, name, col, lane, row=0, *, operator: str, params: dict[str, str | None], result: str, post=None, **kw):
        ps = "".join(
            f'<spiffworkflow:parameter id="{k}" type="any"' + ("" if v is None else f" value={quoteattr(v)}") + " />"
            for k, v in params.items())
        op = (f'<spiffworkflow:serviceTaskOperator id="{operator}" resultVariable="{result}">'
              f"<spiffworkflow:parameters>{ps}</spiffworkflow:parameters></spiffworkflow:serviceTaskOperator>")
        return self._add(nid, "serviceTask", name, col, lane, row, ext=ext(extra=op, post=post), **kw)

    def send(self, nid, name, col, lane, row=0, *, message: str, **kw):
        return self._add(nid, "sendTask", name, col, lane, row, attrs=f' messageRef="{message}"', **kw)

    def gateway(self, nid, name, col, lane, row=0, *, kind="exclusive", default: str | None = None, **kw):
        node = self._add(nid, f"{kind}Gateway", name, col, lane, row, **kw)
        if default:
            self.defaults[nid] = default
        return node

    def catch(self, nid, name, col, lane, row=0, *, definition: str, **kw):
        return self._add(nid, "intermediateCatchEvent", name, col, lane, row, body=definition, **kw)

    def throw(self, nid, name, col, lane, row=0, *, definition: str, **kw):
        return self._add(nid, "intermediateThrowEvent", name, col, lane, row, body=definition, **kw)

    def boundary(self, nid, name, host: str, *, definition: str, interrupting=True, at=0.5, **kw):
        h = self.nodes[host]
        attrs = f' attachedToRef="{host}"' + ("" if interrupting else ' cancelActivity="false"')
        node = self._add(nid, "boundaryEvent", name, h.col, h.lane, h.row, parent=h.parent, attrs=attrs, body=definition, **kw)
        node.attrs, node.at = attrs, at  # type: ignore[attr-defined]
        return node

    def container(self, nid, name, col, lane, row=0, *, tag="subProcess", span=3, **kw):
        node = self._add(nid, tag, name, col, lane, row, **kw)
        node.span = span  # type: ignore[attr-defined]
        return node

    def data_object(self, ref_id: str, obj_id: str, name: str, col, lane, row=0, *, declare=True):
        """A data object reference; declare=False for a second reference to an object already declared."""
        if declare:
            self.process_xml.append(f'<bpmn:dataObject id="{obj_id}" />')
        return self._add(ref_id, "dataObjectReference", name, col, lane, row, attrs=f' dataObjectRef="{obj_id}"')

    def annotate(self, nid: str, text: str, target: str, col: float, lane: str, row: float = 0):
        self.annotations.append((nid, text, target, col, lane, row))

    def group(self, gid: str, label: str, members: list[str]):
        self.root_xml.append(f'<bpmn:category id="Category_{gid}"><bpmn:categoryValue id="CategoryValue_{gid}" value={quoteattr(label)} /></bpmn:category>')
        self.groups.append((gid, label, members))

    def flow(self, source: str, target: str, name: str | None = None, condition: str | None = None,
             fid: str | None = None, over: bool = False):
        self.flows.append(Flow(fid or f"Flow_{source}_{target}", source, target, name, condition, over))

    def message_flow(self, fid: str, source: str, target: str, name: str, message: str | None = None):
        self.message_flows.append((fid, source, target, name, message))

    # ---- layout -----------------------------------------------------------------
    def _lane_tops(self) -> dict[str, tuple[float, int]]:
        tops, y = {}, 60
        for lane, rows in self.lanes:
            tops[lane] = (y, rows)
            y += rows * RH
        return tops

    def _layout(self) -> None:
        tops = self._lane_tops()
        for n in self.nodes.values():
            if n.tag == "boundaryEvent":
                continue
            top, _ = tops[n.lane]
            cx = X0 + n.col * COLW + 50
            cy = top + n.row * RH + RH / 2
            if n.kind == "container":
                span = getattr(n, "span", 3)
                left = X0 + n.col * COLW - 20
                n.bounds = (left, top + n.row * RH + 10, span * COLW - 25, RH - 20)
                continue
            w, h = SIZES[n.kind]
            n.bounds = (cx - w / 2, cy - h / 2, w, h)
        for n in self.nodes.values():
            if n.tag == "boundaryEvent":
                hx, hy, hw, hh = self.nodes[n.attrs.split('attachedToRef="')[1].split('"')[0]].bounds
                n.bounds = (hx + hw * getattr(n, "at", 0.5) - 18, hy + hh - 18, 36, 36)

    @staticmethod
    def _c(b):
        return b[0] + b[2] / 2, b[1] + b[3] / 2

    def _waypoints(self, s: Node, t: Node) -> list[tuple[float, float]]:
        (sx, sy), (tx, ty) = self._c(s.bounds), self._c(t.bounds)
        if s.tag == "boundaryEvent":
            start = (sx, s.bounds[1] + s.bounds[3])
            if ty > start[1]:
                return [start, (sx, ty), (t.bounds[0], ty)] if tx > sx + 5 else [start, (sx, t.bounds[1])]
            return [start, (sx, start[1] + 25), (tx, start[1] + 25), (tx, t.bounds[1] + t.bounds[3])]
        right, left = (s.bounds[0] + s.bounds[2], sy), (t.bounds[0], ty)
        if tx > sx + 5:
            if abs(sy - ty) < 1:
                return [right, left]
            if s.kind == "gateway":  # leave a gateway from the top or bottom towards the target row
                exit_ = (sx, s.bounds[1]) if ty < sy else (sx, s.bounds[1] + s.bounds[3])
                return [exit_, (sx, ty), left]
            if t.kind == "gateway":  # enter a gateway from the top or bottom
                entry = (tx, t.bounds[1]) if sy < ty else (tx, t.bounds[1] + t.bounds[3])
                return [right, (tx, sy), entry]
            mid = (right[0] + left[0]) / 2
            return [right, (mid, sy), (mid, ty), left]
        # backwards: go below both and come up into the target
        low = max(s.bounds[1] + s.bounds[3], t.bounds[1] + t.bounds[3]) + 30
        return [(sx, s.bounds[1] + s.bounds[3]), (sx, low), (tx, low), (tx, t.bounds[1] + t.bounds[3])]

    # ---- XML --------------------------------------------------------------------
    def _node_xml(self, n: Node, indent: str) -> str:
        io = "".join(f"<bpmn:incoming>{f.id}</bpmn:incoming>" for f in self.flows if f.target == n.id)
        io += "".join(f"<bpmn:outgoing>{f.id}</bpmn:outgoing>" for f in self.flows if f.source == n.id)
        name = f" name={quoteattr(n.name)}" if n.name else ""
        default = f' default="{self.defaults[n.id]}"' if n.id in self.defaults else ""
        if n.kind == "container":
            inner = [self._node_xml(c, indent + "  ") for c in self.nodes.values() if c.parent == n.id]
            inner += [self._flow_xml(f, indent + "  ") for f in self.flows if self.nodes[f.source].parent == n.id]
            return (f"{indent}<bpmn:{n.tag} id=\"{n.id}\"{name}{n.attrs}>{n.ext}{io}\n" + "\n".join(inner)
                    + f"\n{indent}</bpmn:{n.tag}>")
        if n.tag == "dataObjectReference":
            return f"{indent}<bpmn:dataObjectReference id=\"{n.id}\"{name}{n.attrs} />"
        return f"{indent}<bpmn:{n.tag} id=\"{n.id}\"{name}{n.attrs}{default}>{n.ext}{io}{n.body}</bpmn:{n.tag}>"

    def _flow_xml(self, f: Flow, indent: str) -> str:
        name = f" name={quoteattr(f.name)}" if f.name else ""
        cond = (f'<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">{x(f.condition)}</bpmn:conditionExpression>'
                if f.condition else "")
        return f'{indent}<bpmn:sequenceFlow id="{f.id}"{name} sourceRef="{f.source}" targetRef="{f.target}">{cond}</bpmn:sequenceFlow>'

    def to_xml(self) -> str:
        self._layout()
        for f in self.flows:
            assert f.source in self.nodes and f.target in self.nodes, f
        tops = self._lane_tops()
        right_edge = max(n.bounds[0] + n.bounds[2] for n in self.nodes.values()) + 80
        pool_h = sum(rows for _, rows in self.lanes) * RH
        pid = self.process_id
        lanes_xml = "".join(
            f'<bpmn:lane id="Lane_{lane.lower()}" name="{lane}">'
            + "".join(f"<bpmn:flowNodeRef>{n.id}</bpmn:flowNodeRef>" for n in self.nodes.values()
                      if n.lane == lane and n.parent is None and n.tag != "dataObjectReference")
            + "</bpmn:lane>" for lane, _ in self.lanes)
        body = [f"    <bpmn:documentation>{x(self.documentation)}</bpmn:documentation>"] if self.documentation else []
        if self.io_spec:
            body.append("    " + self.io_spec)
        body.append(f'    <bpmn:laneSet id="LaneSet_{pid}">{lanes_xml}</bpmn:laneSet>')
        body += [self._node_xml(n, "    ") for n in self.nodes.values() if n.parent is None]
        body += ["    " + p for p in self.process_xml]
        body += [self._flow_xml(f, "    ") for f in self.flows if self.nodes[f.source].parent is None]
        for aid, text, target, *_ in self.annotations:
            body.append(f'    <bpmn:textAnnotation id="{aid}"><bpmn:text>{x(text)}</bpmn:text></bpmn:textAnnotation>')
            body.append(f'    <bpmn:association id="Association_{aid}" sourceRef="{target}" targetRef="{aid}" />')
        for gid, _, _ in self.groups:
            body.append(f'    <bpmn:group id="{gid}" categoryValueRef="CategoryValue_{gid}" />')

        participants = f'<bpmn:participant id="Participant_{pid}" name={quoteattr(self.name)} processRef="{pid}" />'
        partner_xml = ""
        if self.partner:
            ppid, pname = self.partner
            participants += f'<bpmn:participant id="{ppid}" name={quoteattr(pname)} />'
        mflows = "".join(
            f'<bpmn:messageFlow id="{fid}" name={quoteattr(name)} sourceRef="{s}" targetRef="{t}"'
            + (f' messageRef="{m}"' if m else "") + " />" for fid, s, t, name, m in self.message_flows)

        # diagram interchange
        di = [f'<bpmndi:BPMNShape id="Participant_{pid}_di" bpmnElement="Participant_{pid}" isHorizontal="true">'
              f'<dc:Bounds x="{POOL_X}" y="60" width="{right_edge - POOL_X}" height="{pool_h}" /></bpmndi:BPMNShape>']
        for lane, rows in self.lanes:
            top, _ = tops[lane]
            di.append(f'<bpmndi:BPMNShape id="Lane_{lane.lower()}_di" bpmnElement="Lane_{lane.lower()}" isHorizontal="true">'
                      f'<dc:Bounds x="{LANE_X}" y="{top}" width="{right_edge - LANE_X}" height="{rows * RH}" /></bpmndi:BPMNShape>')
        partner_y = 60 + pool_h + 60
        if self.partner:
            di.append(f'<bpmndi:BPMNShape id="{self.partner[0]}_di" bpmnElement="{self.partner[0]}" isHorizontal="true">'
                      f'<dc:Bounds x="{POOL_X}" y="{partner_y}" width="{right_edge - POOL_X}" height="80" /></bpmndi:BPMNShape>')
        for n in self.nodes.values():
            bx, by, bw, bh = n.bounds
            expanded = ' isExpanded="true"' if n.kind == "container" else ""
            di.append(f'<bpmndi:BPMNShape id="{n.id}_di" bpmnElement="{n.id}"{expanded}>'
                      f'<dc:Bounds x="{bx:g}" y="{by:g}" width="{bw:g}" height="{bh:g}" /></bpmndi:BPMNShape>')
        for f in self.flows:
            s_, t_ = self.nodes[f.source], self.nodes[f.target]
            if f.over:
                top = min(s_.bounds[1], t_.bounds[1]) - 22
                (sx_, _), (tx_, _) = self._c(s_.bounds), self._c(t_.bounds)
                way = [(sx_, s_.bounds[1]), (sx_, top), (tx_, top), (tx_, t_.bounds[1])]
            else:
                way = self._waypoints(s_, t_)
            pts = "".join(f'<di:waypoint x="{px:g}" y="{py_:g}" />' for px, py_ in way)
            di.append(f'<bpmndi:BPMNEdge id="{f.id}_di" bpmnElement="{f.id}">{pts}</bpmndi:BPMNEdge>')
        for aid, text, target, col, lane, row in self.annotations:
            top, _ = tops[lane]
            ax, ay = X0 + col * COLW, top + row * RH + 20
            di.append(f'<bpmndi:BPMNShape id="{aid}_di" bpmnElement="{aid}"><dc:Bounds x="{ax:g}" y="{ay:g}" width="180" height="50" /></bpmndi:BPMNShape>')
            tx, ty = self._c(self.nodes[target].bounds)
            di.append(f'<bpmndi:BPMNEdge id="Association_{aid}_di" bpmnElement="Association_{aid}"><di:waypoint x="{tx:g}" y="{ty:g}" /><di:waypoint x="{ax:g}" y="{ay + 25:g}" /></bpmndi:BPMNEdge>')
        for aid, src, dst in self.associations:
            # From border to border, so the line never crosses a shape (it would cover it for clicks).
            sb, tb = self.nodes[src].bounds, self.nodes[dst].bounds
            (sx, sy), (tx, ty) = self._c(sb), self._c(tb)
            if abs(tx - sx) < abs(ty - sy):
                down = ty > sy
                p1 = (sx, sb[1] + sb[3] if down else sb[1])
                p2 = (tx, tb[1] if down else tb[1] + tb[3])
            else:
                right = tx > sx
                p1 = (sb[0] + sb[2] if right else sb[0], sy)
                p2 = (tb[0] if right else tb[0] + tb[2], ty)
            di.append(f'<bpmndi:BPMNEdge id="{aid}_di" bpmnElement="{aid}"><di:waypoint x="{p1[0]:g}" y="{p1[1]:g}" /><di:waypoint x="{p2[0]:g}" y="{p2[1]:g}" /></bpmndi:BPMNEdge>')
        for gid, _, members in self.groups:
            bs = [self.nodes[m].bounds for m in members]
            gx, gy = min(b[0] for b in bs) - 20, min(b[1] for b in bs) - 25
            gw, gh = max(b[0] + b[2] for b in bs) + 20 - gx, max(b[1] + b[3] for b in bs) + 25 - gy
            di.append(f'<bpmndi:BPMNShape id="{gid}_di" bpmnElement="{gid}"><dc:Bounds x="{gx:g}" y="{gy:g}" width="{gw:g}" height="{gh:g}" /></bpmndi:BPMNShape>')
        for fid, s, t, _, _ in self.message_flows:
            node = s if s in self.nodes else t
            nx, _ = self._c(self.nodes[node].bounds)
            nb = self.nodes[node].bounds
            ys = (nb[1] + nb[3], partner_y) if s in self.nodes else (partner_y, nb[1] + nb[3])
            off = 15 if s in self.nodes else -15
            di.append(f'<bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}"><di:waypoint x="{nx + off:g}" y="{ys[0]:g}" /><di:waypoint x="{nx + off:g}" y="{ys[1]:g}" /></bpmndi:BPMNEdge>')

        root = "\n  ".join(self.root_xml)
        newline = "\n"
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by e2e/seed/tools/build_catalog.py: edit the definition there, not this file. -->
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
                  id="Definitions_{pid}" targetNamespace="http://m8flow.org/e2e/catalog">
  <bpmn:collaboration id="Collaboration_{pid}">{participants}{mflows}</bpmn:collaboration>
  {root}
  <bpmn:process id="{pid}" name={quoteattr(self.name)} isExecutable="true">
{newline.join(body)}
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_{pid}">
    <bpmndi:BPMNPlane id="BPMNPlane_{pid}" bpmnElement="Collaboration_{pid}">
      {(newline + "      ").join(di)}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
'''


# ---- DMN ---------------------------------------------------------------------------
def dmn(decision_id: str, name: str, inputs: list[tuple[str, str, str]], outputs: list[tuple[str, str, str]],
        rules: list[tuple[list[str], list[str], str]], hit_policy: str = "FIRST") -> str:
    """inputs/outputs: (label, expression-or-name, typeRef); rules: (input entries, output entries, description).
    An empty input entry matches anything; entries are Python expressions."""
    ins = "".join(
        f'<input id="Input_{i}" label={quoteattr(lbl)}><inputExpression id="InputExpression_{i}" typeRef="{t}"><text>{x(e)}</text></inputExpression></input>'
        for i, (lbl, e, t) in enumerate(inputs, 1))
    outs = "".join(f'<output id="Output_{i}" label={quoteattr(lbl)} name="{n}" typeRef="{t}" />' for i, (lbl, n, t) in enumerate(outputs, 1))
    rs = ""
    for r, (ie, oe, desc) in enumerate(rules, 1):
        rs += f'<rule id="Rule_{r}"><description>{x(desc)}</description>'
        rs += "".join(f'<inputEntry id="InputEntry_{r}_{i}"><text>{x(v)}</text></inputEntry>' for i, v in enumerate(ie, 1))
        rs += "".join(f'<outputEntry id="OutputEntry_{r}_{i}"><text>{x(v)}</text></outputEntry>' for i, v in enumerate(oe, 1))
        rs += "</rule>"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by e2e/seed/tools/build_catalog.py: edit the definition there, not this file. -->
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" xmlns:dmndi="https://www.omg.org/spec/DMN/20191111/DMNDI/"
             xmlns:dc="http://www.omg.org/spec/DMN/20180521/DC/" id="Definitions_{decision_id}" name={quoteattr(name)}
             namespace="http://m8flow.org/e2e/catalog">
  <decision id="{decision_id}" name={quoteattr(name)}>
    <decisionTable id="DecisionTable_{decision_id}" hitPolicy="{hit_policy}">{ins}{outs}{rs}</decisionTable>
  </decision>
  <dmndi:DMNDI><dmndi:DMNDiagram><dmndi:DMNShape dmnElementRef="{decision_id}"><dc:Bounds height="80" width="180" x="160" y="100" /></dmndi:DMNShape></dmndi:DMNDiagram></dmndi:DMNDI>
</definitions>
'''


# ---- forms -------------------------------------------------------------------------
def form(title: str, description: str, fields: dict[str, dict], required: list[str], ui: dict | None = None) -> dict:
    return {"schema": {"title": title, "description": description, "type": "object", "required": required,
                       "properties": fields}, "uischema": ui or {}}


def text(title, **kw): return {"type": "string", "title": title, **kw}
def number(title, **kw): return {"type": "number", "title": title, **kw}
def integer(title, **kw): return {"type": "integer", "title": title, **kw}
def boolean(title, default=False): return {"type": "boolean", "title": title, "default": default}
def choice(title, values: list[str], **kw): return {"type": "string", "title": title, "enum": values, **kw}


def dump(obj) -> str:
    return json.dumps(obj, indent=2) + "\n"
