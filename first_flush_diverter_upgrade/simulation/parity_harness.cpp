// parity_harness.cpp - reads "dry_hours intensity roof_area" lines on stdin and
// prints the firmware's crisp and fuzzy results. Driven by parity_check.py.
#include <cstdio>
#include "diverter_logic.h"
#include "fuzzy_controller.h"
#include "config.h"

int main() {
  double h, i, roof;
  while (std::scanf("%lf %lf %lf", &h, &i, &roof) == 3) {
    DiversionPlan c = calculateDiversionPlan(roof, h, i, BASE_FLUSH_DEPTH_MM, RAIN_GAUGE_MM_PER_TIP);
    DiversionPlan f = calculateFuzzyDiversionPlan(roof, h, i, BASE_FLUSH_DEPTH_MM, RAIN_GAUGE_MM_PER_TIP);
    std::printf("%.9f %lu %.9f %lu %d %d\n", c.multiplier, c.diversionTicks,
                f.multiplier, f.diversionTicks,
                static_cast<int>(f.dryBand), static_cast<int>(f.intensityBand));
  }
  return 0;
}
