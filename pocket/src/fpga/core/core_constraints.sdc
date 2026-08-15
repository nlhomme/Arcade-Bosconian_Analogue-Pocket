#
# user core constraints
#
# PLL outputs 0 (18.432 MHz), 1 (6.144 MHz) and 2 (6.144 MHz, 90 deg) are
# phase-locked off a common 608.27 MHz VCO and the video retiming register
# crosses between them on purpose. They must share a clock group, or
# TimeQuest will treat a real, timed path as asynchronous.
#
# Instance path: apf_top instantiates core_top as `ic`, core_top
# instantiates bosconian_pocket as `bc`, which instantiates mf_pllbase as
# `pll`. Verified against the clock list in output_files/ap_core.sta.rpt.
#
set_clock_groups -asynchronous \
 -group { bridge_spiclk } \
 -group { clk_74a } \
 -group { clk_74b } \
 -group { ic|bc|pll|mf_pllbase_inst|altera_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk \
          ic|bc|pll|mf_pllbase_inst|altera_pll_i|general[1].gpll~PLL_OUTPUT_COUNTER|divclk \
          ic|bc|pll|mf_pllbase_inst|altera_pll_i|general[2].gpll~PLL_OUTPUT_COUNTER|divclk }
