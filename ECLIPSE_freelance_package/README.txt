ECLIPSE - PCB design package
Breloque - August 2026

--------------------------------------------------------------------
WHAT IS IN THIS PACKAGE
--------------------------------------------------------------------

1_brief/
    ECLIPSE_PCB_brief_EN.pdf    <- START HERE. The full brief in English.
    ECLIPSE_PCB_brief_FR.pdf       Same document in French.

2_previous_design_v21_REFERENCE_ONLY/
    The KiCad project of the board I designed myself and that FAILED.
    Provided as documentation only - see the warning below.


--------------------------------------------------------------------
IMPORTANT - ABOUT THE PREVIOUS DESIGN
--------------------------------------------------------------------

The KiCad project in folder 2 is the board that was manufactured,
assembled in 5 units, and DESTROYED on first power-up.

It is included so you can see what was intended functionally, and so
you can verify for yourself the faults listed in section 4 of the
brief - several of them are measurable directly in these files.

DO NOT reuse this design as a starting point. It contains, among
other issues, a regulator enable pin tied to 12 V on a pin rated 6 V
absolute maximum, unconnected microcontroller strapping pins, and a
module footprint that cannot be inspected or reworked.

You are expected to redesign from scratch. You are entirely free on
components, architecture and values.


--------------------------------------------------------------------
HOW TO OPEN THE PREVIOUS DESIGN
--------------------------------------------------------------------

Open  eclipse_v21.kicad_pro  in KiCad (version 8 or newer).

The project is self-contained: the footprint library (eclipse.pretty)
and the symbol library (easyeda2kicad.kicad_sym) are included in the
same folder, and fp-lib-table / sym-lib-table point to them with
relative paths. Nothing else needs to be installed.

Board: 58 x 24 mm, 2 layers, FR-4, 1.6 mm.

BOM_eclipse_v21.csv and CPL_eclipse_v21.csv are the bill of materials
and pick-and-place files that were used for assembly (JLCPCB format).


--------------------------------------------------------------------
NOT INCLUDED
--------------------------------------------------------------------

- Gerber files: not included, as they describe the failed board and
  are of no use for a new design. They can be regenerated from the
  KiCad project if you want to look at them.

- Firmware: I supply it separately once the hardware is defined.

- BRELOQUE logo: high-resolution file supplied on request, for the
  silkscreen.

- LED strip datasheet: available on request. Please ask for it before
  sizing the LED channels - see the note in section 3 of the brief.
