# Rapid Device Support Development With P4P and AI

**A. Sukhanov**  
Brookhaven National Laboratory, Upton, NY, USA

---

## Abstract

This paper describes `epicsdev`, a Python framework that dramatically reduces the effort required to create EPICS PVAccess servers using the [p4p](https://epics-base.github.io/p4p/) library, and demonstrates how pairing it with AI code-generation tools enables instrument integration in under an hour.

Modern EPICS deployments increasingly favor PVAccess over legacy Channel Access, but writing boilerplate server code remains tedious. `epicsdev` addresses this by providing a thin, declarative layer on top of `p4p`: device PVs are described as a compact list of `[name, description, initial_value, attributes]` tuples; the framework then handles server creation, periodic updates, autosave/restore, IOC-stats heartbeat, and PV-put logging automatically. A built-in multi-channel waveform generator (`epicsdev.multiadc`) exercises the framework under stress — it can sustain **10,000 waveforms per second** across configurable channels (each with 100 or more samples) while simultaneously publishing 40,000 scalar parameters per second, making it a useful benchmark for client-side performance testing.

Because all device logic lives in a small, well-structured Python file with a predictable pattern, large-language-model (LLM) assistants such as GitHub Copilot can replicate that pattern for any new instrument given only a manufacturer's programming manual and the name of an existing `epicsdev`-based server as a template. The workflow is:

1. Create a new GitHub repository.
2. Give the AI a prompt that references an existing server (e.g. `epicsdev_rigol_scope`) and a link to the instrument's SCPI manual.
3. The AI generates the complete server as a pull request, typically within **20–40 minutes**.
4. The developer reviews, runs a brief acceptance test, and merges.

This approach was validated with [`epicsdev_tektronix`](https://github.com/ASukhanov/epicsdev_tektronix), a PVAccess server for Tektronix MSO 4/5/6 Series mixed-signal oscilloscopes. The AI-generated code was **~99% correct on the first attempt** and required only minor corrections before production use. The resulting server supports waveform acquisition, SCPI-based control (trigger mode, horizontal/vertical scales, channel coupling, offset, and termination), and real-time monitoring via pypeto or Phoebus displays. Measured acquisition throughput for six channels at one million samples each is **12 MB/s** (acquisition time ≈ 2 s), which comfortably meets typical oscilloscope use cases.

The combination of `epicsdev`'s structured template and AI-assisted code generation lowers the barrier for instrument integration, reduces development time from days to under an hour, and produces maintainable, idiomatic Python code that follows consistent project conventions.

---

*Keywords: EPICS, PVAccess, p4p, device support, AI, GitHub Copilot, oscilloscope, Tektronix*
