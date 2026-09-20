# Synthetic directional static margin

POLAR-003 adds seven nonuniform beta points from -8 to +8 degrees at constant
ALPHA = 3 degrees, Mach = 0.2 and Reynolds = 7.0518518519e6. Select this polar
in the launcher and choose **Directional** in the Static margin tab.

The Stability-axis coefficients follow these analytical relations (beta in radians):

- CYS = -0.8 beta
- CNS = +0.12 beta
- -100 dCNS/dCYS = **+15% BREF** at the original moment reference.

The margin is the negative derivative, consistent with the longitudinal definition.
No absolute value is applied. CNS already uses BREF in its normalization, so the
derivative is multiplied by -100 without dividing by BREF a second time.

Body and Wind coefficients are rotated consistently from Stability axes. The
reference dimensions match POLAR-001: BREF = 10 m and CREF = 1.5555555556 m.
Moving Xref aft by 1 m gives 15 - 10 cos(3 degrees) = approximately +5.014% BREF.
The dashboard's validated moment-transfer calculation is used for this check.

This is analytical test data, not a solver prediction. ADF and infout are supplied;
there are deliberately no solver histories or load/Cp distributions for POLAR-003.
The dashboard should still display its coefficients and directional margin.
POLAR-001 and POLAR-002 retain the longitudinal checks (10% CREF).

Reproduce the files with `python 00-SUPPORT/create_directional_fixture.py`.
The script refuses to overwrite a differing existing fixture. Expected values
are in `expected_directional_values.json`; `validate_test_data.py` checks them.
