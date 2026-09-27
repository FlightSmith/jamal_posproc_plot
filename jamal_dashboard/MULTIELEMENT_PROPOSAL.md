# Multi-element pressure sections — proposal only

No multi-element splitting or synthetic wing/flap fixture is implemented in v25.9.
The user requested discussion before this work begins.

## Why one global X minimum/maximum is insufficient

Main-wing and flap surfaces can overlap in X. Two columns containing X and pressure
do not identify which element a sample belongs to. Even upper/lower labels cannot
be recovered reliably from pressure magnitude: negative or reversed loading is valid.
Matched geometry helps only when contour boundaries and point correspondence survive
the export. A deflected flap also needs its own chord direction; global X extrema
need not identify its aerodynamic LE and TE.

## Proposed input and calculation

1. Preserve a separate, named contour for each element. Prefer element IDs and
   point IDs shared by geometry/pressure, or separate files/blocks with guaranteed
   matching row order. A sidecar with explicit point ranges can support an unchanged
   two-column format if the exporter provides stable ranges.
2. Associate pressure and geometry using those IDs/order; never nearest X alone.
3. Specify each element's local LE/TE and positive normal, or validate a geometry
   detector against representative real files before accepting its output.
4. Split each named contour into upper/lower in that local frame. Use one curve style
   per source; show element and surface names in hover.
5. Integrate the closed pressure contour of every element and sum force components
   in the common body frame before projecting to lift. Preserve orientation and
   span-density transformations for canted elements.
6. Normalize combined cl with an explicitly selected original/reference section
   chord. Do not silently replace it with the overall wing/flap X bounding box.
7. If element identity, connectivity or reference geometry is unresolved, omit the
   combined load with an explanation. Do not invent a continuous contour.

Before implementation, inspect one representative wing-plus-flap pressure file and
its section geometry, including any curve blocks/zone labels. Confirm intended
normalization chord and coordinate conventions. A synthetic fixture can then cover
overlapping X, flap deflection, reversed traversal and different mesh densities.

## Sources

- [NASA: aerodynamic force](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/aerodynamic-force/)
  explains integration of pressure into force and its lift/drag components.
- [Ansys Fluent: XY plots](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/flu_ug/flu_ug_sec_graphics_plot.html)
  documents labeled curves and abscissa ordering. Preserve contour/zone identity;
  global abscissa sorting cannot substitute for connectivity.

The proposed data contract and rejection rules are engineering recommendations
derived from those principles and inspection of the existing JAMAL fixtures.
