"""Exact broad-phase pruning: exhaustive oracles and bounded work, not timing."""
import math
import random
import unittest
from unittest.mock import patch

import jamal_distributions as dist


def exhaustive_pairs(segments, tolerance, other_segments=None):
    """Independent exhaustive enumeration, deliberately without any pruning."""
    if other_segments is None:
        return ((i, j) for i in range(len(segments)) for j in range(i+1, len(segments)))
    return ((i, j) for i in range(len(segments)) for j in range(len(other_segments)))


def box_oracle(segments, tolerance, other_segments=None):
    result = set()
    other = segments if other_segments is None else other_segments
    for i, j in exhaustive_pairs(segments, tolerance, other_segments):
        a, b = segments[i]
        c, d = other[j]
        if all(max(a[axis], b[axis])+tolerance >= min(c[axis], d[axis])
               and max(c[axis], d[axis])+tolerance >= min(a[axis], b[axis])
               for axis in (0, 1)):
            result.add((i, j))
    return result


def edges(vertices):
    return list(zip(vertices, vertices[1:]+vertices[:1]))


def densify(vertices, factor):
    return [(a[0]+(b[0]-a[0])*i/factor, a[1]+(b[1]-a[1])*i/factor)
            for a, b in edges(vertices) for i in range(factor)]


def topology_result(geometry):
    try:
        return 'ok', dist.section_topology(geometry)
    except ValueError as error:
        return 'error', str(error)


class TopologyPruningTests(unittest.TestCase):
    def test_boxes_match_independent_exhaustive_oracle(self):
        randomizer = random.Random(29102026)
        for count in (0, 1, 8, 9, 37, 120):
            segments = [((randomizer.uniform(-2, 2), randomizer.uniform(-1, 1)),
                         (randomizer.uniform(-2, 2), randomizer.uniform(-1, 1)))
                        for _ in range(count)]
            other = [((x+.4, y+1), (u+.4, v+1)) for (x, y), (u, v) in segments]
            for second in (None, [], other):
                with self.subTest(count=count, cross=second is not None):
                    actual = list(dist._segment_box_candidates(segments, 1e-8, second))
                    self.assertEqual(len(actual), len(set(actual)), 'Pairs must be unique')
                    self.assertEqual(set(actual), box_oracle(segments, 1e-8, second))

    def test_bbox_tolerance_boundaries_and_degenerate_segments_are_retained(self):
        tolerance = 1e-8
        segments = [((0., 0.), (1., 0.)), ((1., 0.), (1., 0.)),
                    ((0., tolerance), (1., tolerance)),
                    ((0., math.nextafter(tolerance, math.inf)), (1., 2*tolerance))]
        # More than one leaf ensures both group bounds and segment bounds matter.
        segments += [((3.+i, 0.), (3.+i, 1.)) for i in range(20)]
        for source in (segments, list(reversed(segments))):
            self.assertEqual(set(dist._segment_box_candidates(source, tolerance)),
                             box_oracle(source, tolerance))

    def test_randomized_topology_matches_exhaustive_validation(self):
        randomizer = random.Random(29092026)
        accepted = rejected = 0
        for trial in range(80):
            count = randomizer.randrange(7, 45)
            radii = [randomizer.uniform(.7, 1.3) for _ in range(count)]
            points = [(r*math.cos(2*math.pi*i/count), .18*r*math.sin(2*math.pi*i/count))
                      for i, r in enumerate(radii)]
            if trial % 4 == 1:
                randomizer.shuffle(points)  # Crossings, usually with nonzero area.
            elif trial % 4 == 2:
                points = list(reversed(points))
            start = randomizer.randrange(count)
            points = points[start:]+points[:start]
            if trial % 5 == 0:
                points.insert(2, points[1])  # Retain repeated paired pressure rows.
            contour = points+points[:1]
            if trial % 4 == 3:
                # Disjoint, touching/intersecting and nested second contours.
                scale, offset = ((.4, 2.), (.8, .5), (.2, 0.))[trial % 3]
                second = [(x*scale+offset, y*scale) for x, y in contour]
                contour += second
            actual = topology_result(contour)
            with patch.object(dist, '_segment_box_candidates', exhaustive_pairs):
                expected = topology_result(contour)
            with self.subTest(trial=trial):
                self.assertEqual(actual, expected)
            accepted += actual[0] == 'ok'
            rejected += actual[0] == 'error'
        self.assertGreater(accepted, 20)
        self.assertGreater(rejected, 20)

    def test_legacy_open_contour_and_invalid_error_precedence_match(self):
        cases = [
            [(1., .02), (.5, .1), (0., 0.), (.5, -.1), (1., -.02)],
            [(0., 0.), (1., .1), (.8, .08), (.4, -.1), (0., 0.)],
            [(0., 0.), (1., .1), (.5, .05), (1., -.1), (0., 0.)],
            [(0., 0.), (1., .2), (0., .2), (1., 0.), (0., 0.)],
            [(0., 0.), (1., 0.), (1., 1.), (0., 1.), (0., 0.),
             (1.+1e-8, 0.), (2., 0.), (2., 1.), (1.+1e-8, 1.), (1.+1e-8, 0.)],
        ]
        for contour in cases:
            actual = topology_result(contour)
            with patch.object(dist, '_segment_box_candidates', exhaustive_pairs):
                expected = topology_result(contour)
            self.assertEqual(actual, expected)

    def test_dense_cove_uses_bounded_bbox_work_without_dropping_pairs(self):
        # Repeated X along the cove defeats a simple one-dimensional X sweep.
        corners = [(0., 0.), (.25, .1), (.8, .08), (1., .05),
                   (.9, .05), (.9, -.05), (1., -.05), (.8, -.08), (.25, -.1)]
        work = []
        exact_overlap = dist._segment_boxes_overlap
        for factor in (128, 256, 512):
            segments = edges(densify(corners, factor))
            calls = 0

            def counted(a, b, tolerance):
                nonlocal calls
                calls += 1
                return exact_overlap(a, b, tolerance)

            with patch.object(dist, '_segment_boxes_overlap', counted):
                pairs = set(dist._segment_box_candidates(segments, 1e-8))
            # All adjacent edges must remain candidates. A few boxes beside
            # corners can overlap without their segments actually touching.
            expected = {(i, i+1) for i in range(len(segments)-1)}
            expected.add((0, len(segments)-1))
            self.assertTrue(expected <= pairs)
            self.assertLess(len(pairs), 2*len(segments))
            self.assertLess(calls, 30*len(segments))
            work.append(calls)
        self.assertLess(work[1], 2.6*work[0])
        self.assertLess(work[2], 2.6*work[1])


if __name__ == '__main__':
    unittest.main()
