# OCC Cybersecurity Protocol Evaluation — Research

Research documentation for an internship investigating the performance,
security, resilience and interoperability of industrial communication
protocols in an Operations Control Center (OCC).

**Host institution:** Otto von Guericke University Magdeburg

**Academic programme:** M.Sc. Information and Communication Systems,
Chemnitz University of Technology (TU Chemnitz).

## Research objective

Study and compare MQTT, OPC UA and DDS for telemetry communication between
embedded vehicle nodes and an OCC. Investigate authentication, integrity,
encryption, network impairment, resource overhead and controlled
cybersecurity attacks using measurable performance indicators.

## Repository branches

| Branch | Purpose |
|---|---|
| `main` | Research foundation, literature review, methodology and references |
| `testbed` | Implemented hardware, software, experiments and recorded evidence |

[Open the engineering implementation](https://github.com/moulikhamahendran/OCC-Cybersecurity-Protocol-Evaluation/tree/testbed)

## Research directory guide

| Directory | Contents |
|---|---|
| [Literature review](literature_review/) | Systematic review, PRISMA, research questions and screening |
| [Methodology](methodology/) | Experimental design, KPI definitions and validation approach |
| [Documentation](docs/) | Research overview, security framework and protocol comparisons |
| [Datasets](datasets/) | Dataset references, sources and testbed notes |
| [Figures](figures/) | Architecture and research illustrations |
| [References](references/) | Bibliography, selected publications and citation notes |
| [Progress](progress/) | Historical plans, milestones, timeline and challenges |

## Research methodology

The research combines a literature-based investigation with controlled
evaluation of MQTT, OPC UA and DDS.

Principal evaluation dimensions include latency, jitter, throughput,
application-level delivery, CPU and memory usage, security overhead,
network impairments and protocol-specific attack behavior.

Key documents:

- [Project overview](docs/Project_Overview.md)
- [Research methodology](methodology/experimental_design.md)
- [Evaluation metrics](methodology/evaluation_metrics.md)
- [Protocol comparison framework](methodology/protocol_comparison_framework.md)
- [KPI definition](docs/KPI_Definition.md)
- [Research references](references/reference.bib)

## Engineering evaluation and evidence

The implementation uses a Raspberry Pi 5 as the OCC host, two ESP32
legitimate vehicle nodes and one ESP32 attacker node.

Implementation sources, technical setup instructions, security-profile
mappings, experiment runners, recorded results and comparison figures
are maintained on the `testbed` branch.

[View consolidated KPI comparison](https://github.com/moulikhamahendran/OCC-Cybersecurity-Protocol-Evaluation/tree/testbed/testbed/software/results/final_kpi_comparison/20261017T104713Z)

Historical research notes and roadmaps in this branch retain their
original planning context. They are not a current technical
acceptance report.

## Scope and limitations

This work is an experimental cybersecurity evaluation testbed, not a
production-certified industrial control system. Its results must be
interpreted in the context of the documented experimental methodology.

Linux robot/factory integration and the separate SmartRegion/AAS
logistics project are outside this internship's implementation scope.

Controlled attacks must target only authorized laboratory services.
