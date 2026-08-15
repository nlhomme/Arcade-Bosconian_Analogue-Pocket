//
// Bosconian glue for the Analogue Pocket.
//
// Knows nothing about APF: core_top.v owns the bridge and hands us an
// already-decoded interface. Everything here is clocks, video retiming,
// audio conversion, input mapping, and the VHDL core instantiation.
//
`default_nettype none

module bosconian_pocket (
    input wire clk_74a,
    input wire reset_n,

    // ROM stream from the APF dataslot, ioctl-compatible
    input wire [15:0] dn_addr,
    input wire  [7:0] dn_data,
    input wire        dn_wr,
    input wire        dn_active,

    // DIP switches, same polarity as the MiSTer .mra values
    input wire [7:0] dip_a,
    input wire [7:0] dip_b,
    input wire       self_test,
    input wire       service,

    input wire [15:0] cont1_key,
    input wire [15:0] cont2_key,

    output wire [23:0] video_rgb,
    output wire        video_de,
    output wire        video_hs,
    output wire        video_vs,
    output wire        video_skip,
    output wire        video_rgb_clock,
    output wire        video_rgb_clock_90,

    output wire [15:0] audio_l,
    output wire [15:0] audio_r,

    // core_top gates the APF boot/setup status bits on this
    output wire pll_locked
);

  ////////////////////////////////////////////////////////////////////////
  // Clocks
  //
  // 18.432 MHz is the authentic Namco rate; MiSTer runs this core at a
  // flat 18.000 MHz, which is about 2.3% slow.
  ////////////////////////////////////////////////////////////////////////

  wire clk_18432;
  wire clk_6144;
  wire clk_6144_90;

  mf_pllbase pll (
      .refclk(clk_74a),
      .rst   (1'b0),

      .outclk_0(clk_18432),
      .outclk_1(clk_6144),
      .outclk_2(clk_6144_90),
      .outclk_3(),
      .outclk_4(),

      .locked(pll_locked)
  );

  assign video_rgb_clock    = clk_6144;
  assign video_rgb_clock_90 = clk_6144_90;
  assign video_skip         = 1'b0;

  // Reset while the PLL is unlocked, while APF holds us in reset, and for
  // the whole ROM download.
  wire reset_n_s;
  synch_3 s_reset (reset_n, reset_n_s, clk_18432);

  wire pll_locked_s;
  synch_3 s_lock (pll_locked, pll_locked_s, clk_18432);

  wire dn_active_s;
  synch_3 s_dn (dn_active, dn_active_s, clk_18432);

  wire core_reset = ~reset_n_s | ~pll_locked_s | dn_active_s;

  ////////////////////////////////////////////////////////////////////////
  // Inputs
  //
  // Everything here arrives in the clk_74a domain, which the .sdc cuts as
  // a false path against the core clock -- nothing times these. Cross them
  // into clk_18432 before decoding. The DIPs and the two switches are
  // static after load, but they sit on the same boundary and a synchroniser
  // costs nothing.
  //
  // APF cont1_key bit order:
  //   0 up, 1 down, 2 left, 3 right, 4 A, 5 B, 6 X, 7 Y,
  //   8 L1, 9 R1, 10 L2, 11 R2, 12 L3, 13 R3, 14 select, 15 start
  ////////////////////////////////////////////////////////////////////////

  wire [15:0] cont1_key_s, cont2_key_s;
  synch_3 #(16) s_c1 (cont1_key, cont1_key_s, clk_18432);
  synch_3 #(16) s_c2 (cont2_key, cont2_key_s, clk_18432);

  wire [7:0] dip_a_s, dip_b_s;
  wire self_test_s, service_s;
  synch_3 #(8) s_dipa (dip_a, dip_a_s, clk_18432);
  synch_3 #(8) s_dipb (dip_b, dip_b_s, clk_18432);
  synch_3 s_selftest (self_test, self_test_s, clk_18432);
  synch_3 s_service (service, service_s, clk_18432);

  wire [15:0] joy = cont1_key_s | cont2_key_s;

  wire m_up    = joy[0];
  wire m_down  = joy[1];
  wire m_left  = joy[2];
  wire m_right = joy[3];
  wire m_fire  = joy[4] | joy[5] | joy[6] | joy[7];

  wire m_coin1  = cont1_key_s[14];
  wire m_coin2  = cont2_key_s[14];
  wire m_start1 = cont1_key_s[15];
  wire m_start2 = cont2_key_s[15] | cont1_key_s[8];

  ////////////////////////////////////////////////////////////////////////
  // Core
  ////////////////////////////////////////////////////////////////////////

  wire [2:0] core_r, core_g;
  wire [1:0] core_b;
  wire hsync_n, vsync_n, hblank_n, vblank_n;
  wire [15:0] core_audio;

  bosconian bosconian (
      .clock_18(clk_18432),
      .reset   (core_reset),

      .dn_addr(dn_addr),
      .dn_data(dn_data),
      .dn_wr  (dn_wr),

      .video_r      (core_r),
      .video_g      (core_g),
      .video_b      (core_b),
      .video_hsync_n(hsync_n),
      .video_vsync_n(vsync_n),
      .video_hblank_n(hblank_n),
      .video_vblank_n(vblank_n),

      .audio(core_audio),

      .self_test(self_test_s),
      .service  (service_s),

      .coin1(m_coin1),
      .coin2(m_coin2),

      .start1(m_start1),
      .up1(m_up), .down1(m_down), .left1(m_left), .right1(m_right),
      .fire1(m_fire),

      .start2(m_start2),
      .up2(m_up), .down2(m_down), .left2(m_left), .right2(m_right),
      .fire2(m_fire),

      // The core inverts internally, same as the MiSTer top level.
      .dip_switch_a(~dip_a_s),
      .dip_switch_b(~dip_b_s),

      // MiSTer analog-output tweaks; meaningless on the Pocket.
      .h_offset(4'd0),
      .v_offset(4'd0),
      .pause   (1'b0)
  );

  ////////////////////////////////////////////////////////////////////////
  // Video retiming
  //
  // The core produces pixels in the 18.432 MHz domain on a 6 MHz enable.
  // clk_6144 is the same PLL VCO (608.27 MHz) divided by 99 while clk_18432
  // is divided by 33: an exact 3:1 ratio off one VCO, so edges are
  // coincident and a single register stage is sufficient. The .sdc must
  // place them in the same clock group, or that crossing goes untimed.
  //
  // If pixels come out sheared or doubled, this register is sampling on
  // the wrong phase of the core's pixel pipeline. Do NOT reach for the
  // core's `video_ce` output: it is high at slots 0 and 3, which is the
  // MISALIGNED phase. The pipeline actually advances on `video_6M_ena`
  // (slots 2 and 5), which rtl/bosconian.vhd does not bring out to a port
  // -- and rtl/ is read-only here. The knob to turn instead is
  // phase_shift1 in mf_pllbase_0002.v: walk the 6.144 MHz capture clock in
  // picoseconds until it samples mid-pixel. One 18.432 MHz period is
  // 54257 ps, so a whole slot is that much of shift.
  ////////////////////////////////////////////////////////////////////////

  reg [23:0] rgb_r;
  reg de_r, hs_r, vs_r;

  always @(posedge clk_6144) begin
    // 3:3:2 to 8:8:8 by bit replication, matching MiSTer's arcade_video.
    rgb_r <= {
      core_r, core_r, core_r[2:1],
      core_g, core_g, core_g[2:1],
      core_b, core_b, core_b, core_b
    };
    de_r <= hblank_n & vblank_n;
    hs_r <= ~hsync_n;
    vs_r <= ~vsync_n;
  end

  assign video_rgb = de_r ? rgb_r : 24'h0;
  assign video_de  = de_r;
  assign video_hs  = hs_r;
  assign video_vs  = vs_r;

  ////////////////////////////////////////////////////////////////////////
  // Audio
  //
  // The core emits UNSIGNED samples (MiSTer sets AUDIO_S = 0). I2S wants
  // signed, so flip the high bit. Getting this wrong gives a full-scale
  // DC offset and clipping, not silence.
  ////////////////////////////////////////////////////////////////////////

  wire [15:0] audio_signed = {~core_audio[15], core_audio[14:0]};

  assign audio_l = audio_signed;
  assign audio_r = audio_signed;

endmodule

`default_nettype wire
