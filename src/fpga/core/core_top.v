//
// User core top-level
//
// Instantiated by the real top-level: apf_top
//

`default_nettype none

module core_top (

    //
    // physical connections
    //

    ///////////////////////////////////////////////////
    // clock inputs 74.25mhz. not phase aligned, so treat these domains as asynchronous

    input wire clk_74a,  // mainclk1
    input wire clk_74b,  // mainclk1 

    ///////////////////////////////////////////////////
    // cartridge interface
    // switches between 3.3v and 5v mechanically
    // output enable for multibit translators controlled by pic32

    // GBA AD[15:8]
    inout  wire [7:0] cart_tran_bank2,
    output wire       cart_tran_bank2_dir,

    // GBA AD[7:0]
    inout  wire [7:0] cart_tran_bank3,
    output wire       cart_tran_bank3_dir,

    // GBA A[23:16]
    inout  wire [7:0] cart_tran_bank1,
    output wire       cart_tran_bank1_dir,

    // GBA [7] PHI#
    // GBA [6] WR#
    // GBA [5] RD#
    // GBA [4] CS1#/CS#
    //     [3:0] unwired
    inout  wire [7:4] cart_tran_bank0,
    output wire       cart_tran_bank0_dir,

    // GBA CS2#/RES#
    inout  wire cart_tran_pin30,
    output wire cart_tran_pin30_dir,
    // when GBC cart is inserted, this signal when low or weak will pull GBC /RES low with a special circuit
    // the goal is that when unconfigured, the FPGA weak pullups won't interfere.
    // thus, if GBC cart is inserted, FPGA must drive this high in order to let the level translators
    // and general IO drive this pin.
    output wire cart_pin30_pwroff_reset,

    // GBA IRQ/DRQ
    inout  wire cart_tran_pin31,
    output wire cart_tran_pin31_dir,

    // infrared
    input  wire port_ir_rx,
    output wire port_ir_tx,
    output wire port_ir_rx_disable,

    // GBA link port
    inout  wire port_tran_si,
    output wire port_tran_si_dir,
    inout  wire port_tran_so,
    output wire port_tran_so_dir,
    inout  wire port_tran_sck,
    output wire port_tran_sck_dir,
    inout  wire port_tran_sd,
    output wire port_tran_sd_dir,

    ///////////////////////////////////////////////////
    // cellular psram 0 and 1, two chips (64mbit x2 dual die per chip)

    output wire [21:16] cram0_a,
    inout  wire [ 15:0] cram0_dq,
    input  wire         cram0_wait,
    output wire         cram0_clk,
    output wire         cram0_adv_n,
    output wire         cram0_cre,
    output wire         cram0_ce0_n,
    output wire         cram0_ce1_n,
    output wire         cram0_oe_n,
    output wire         cram0_we_n,
    output wire         cram0_ub_n,
    output wire         cram0_lb_n,

    output wire [21:16] cram1_a,
    inout  wire [ 15:0] cram1_dq,
    input  wire         cram1_wait,
    output wire         cram1_clk,
    output wire         cram1_adv_n,
    output wire         cram1_cre,
    output wire         cram1_ce0_n,
    output wire         cram1_ce1_n,
    output wire         cram1_oe_n,
    output wire         cram1_we_n,
    output wire         cram1_ub_n,
    output wire         cram1_lb_n,

    ///////////////////////////////////////////////////
    // sdram, 512mbit 16bit

    output wire [12:0] dram_a,
    output wire [ 1:0] dram_ba,
    inout  wire [15:0] dram_dq,
    output wire [ 1:0] dram_dqm,
    output wire        dram_clk,
    output wire        dram_cke,
    output wire        dram_ras_n,
    output wire        dram_cas_n,
    output wire        dram_we_n,

    ///////////////////////////////////////////////////
    // sram, 1mbit 16bit

    output wire [16:0] sram_a,
    inout  wire [15:0] sram_dq,
    output wire        sram_oe_n,
    output wire        sram_we_n,
    output wire        sram_ub_n,
    output wire        sram_lb_n,

    ///////////////////////////////////////////////////
    // vblank driven by dock for sync in a certain mode

    input wire vblank,

    ///////////////////////////////////////////////////
    // i/o to 6515D breakout usb uart

    output wire dbg_tx,
    input  wire dbg_rx,

    ///////////////////////////////////////////////////
    // i/o pads near jtag connector user can solder to

    output wire user1,
    input  wire user2,

    ///////////////////////////////////////////////////
    // RFU internal i2c bus 

    inout  wire aux_sda,
    output wire aux_scl,

    ///////////////////////////////////////////////////
    // RFU, do not use
    output wire vpll_feed,


    //
    // logical connections
    //

    ///////////////////////////////////////////////////
    // video, audio output to scaler
    output wire [23:0] video_rgb,
    output wire        video_rgb_clock,
    output wire        video_rgb_clock_90,
    output wire        video_de,
    output wire        video_skip,
    output wire        video_vs,
    output wire        video_hs,

    output wire audio_mclk,
    input  wire audio_adc,
    output wire audio_dac,
    output wire audio_lrck,

    ///////////////////////////////////////////////////
    // bridge bus connection
    // synchronous to clk_74a
    output wire        bridge_endian_little,
    input  wire [31:0] bridge_addr,
    input  wire        bridge_rd,
    output reg  [31:0] bridge_rd_data,
    input  wire        bridge_wr,
    input  wire [31:0] bridge_wr_data,

    ///////////////////////////////////////////////////
    // controller data
    // 
    // key bitmap:
    //   [0]    dpad_up
    //   [1]    dpad_down
    //   [2]    dpad_left
    //   [3]    dpad_right
    //   [4]    face_a
    //   [5]    face_b
    //   [6]    face_x
    //   [7]    face_y
    //   [8]    trig_l1
    //   [9]    trig_r1
    //   [10]   trig_l2
    //   [11]   trig_r2
    //   [12]   trig_l3
    //   [13]   trig_r3
    //   [14]   face_select
    //   [15]   face_start
    // joy values - unsigned
    //   [ 7: 0] lstick_x
    //   [15: 8] lstick_y
    //   [23:16] rstick_x
    //   [31:24] rstick_y
    // trigger values - unsigned
    //   [ 7: 0] ltrig
    //   [15: 8] rtrig
    //
    input wire [15:0] cont1_key,
    input wire [15:0] cont2_key,
    input wire [15:0] cont3_key,
    input wire [15:0] cont4_key,
    input wire [31:0] cont1_joy,
    input wire [31:0] cont2_joy,
    input wire [31:0] cont3_joy,
    input wire [31:0] cont4_joy,
    input wire [15:0] cont1_trig,
    input wire [15:0] cont2_trig,
    input wire [15:0] cont3_trig,
    input wire [15:0] cont4_trig

);

  // not using the IR port, so turn off both the LED, and
  // disable the receive circuit to save power
  assign port_ir_tx              = 0;
  assign port_ir_rx_disable      = 1;

  // bridge endianness
  assign bridge_endian_little    = 0;

  // cart is unused, so set all level translators accordingly
  // directions are 0:IN, 1:OUT
  assign cart_tran_bank3         = 8'hzz;
  assign cart_tran_bank3_dir     = 1'b0;
  assign cart_tran_bank2         = 8'hzz;
  assign cart_tran_bank2_dir     = 1'b0;
  assign cart_tran_bank1         = 8'hzz;
  assign cart_tran_bank1_dir     = 1'b0;
  assign cart_tran_bank0         = 4'hf;
  assign cart_tran_bank0_dir     = 1'b1;
  assign cart_tran_pin30         = 1'b0;  // reset or cs2, we let the hw control it by itself
  assign cart_tran_pin30_dir     = 1'bz;
  assign cart_pin30_pwroff_reset = 1'b0;  // hardware can control this
  assign cart_tran_pin31         = 1'bz;  // input
  assign cart_tran_pin31_dir     = 1'b0;  // input

  // link port is input only
  assign port_tran_so            = 1'bz;
  assign port_tran_so_dir        = 1'b0;  // SO is output only
  assign port_tran_si            = 1'bz;
  assign port_tran_si_dir        = 1'b0;  // SI is input only
  assign port_tran_sck           = 1'bz;
  assign port_tran_sck_dir       = 1'b0;  // clock direction can change
  assign port_tran_sd            = 1'bz;
  assign port_tran_sd_dir        = 1'b0;  // SD is input and not used

  // tie off the rest of the pins we are not using
  assign cram0_a                 = 'h0;
  assign cram0_dq                = {16{1'bZ}};
  assign cram0_clk               = 0;
  assign cram0_adv_n             = 1;
  assign cram0_cre               = 0;
  assign cram0_ce0_n             = 1;
  assign cram0_ce1_n             = 1;
  assign cram0_oe_n              = 1;
  assign cram0_we_n              = 1;
  assign cram0_ub_n              = 1;
  assign cram0_lb_n              = 1;

  assign cram1_a                 = 'h0;
  assign cram1_dq                = {16{1'bZ}};
  assign cram1_clk               = 0;
  assign cram1_adv_n             = 1;
  assign cram1_cre               = 0;
  assign cram1_ce0_n             = 1;
  assign cram1_ce1_n             = 1;
  assign cram1_oe_n              = 1;
  assign cram1_we_n              = 1;
  assign cram1_ub_n              = 1;
  assign cram1_lb_n              = 1;

  assign dram_a                  = 'h0;
  assign dram_ba                 = 'h0;
  assign dram_dq                 = {16{1'bZ}};
  assign dram_dqm                = 'h0;
  assign dram_clk                = 'h0;
  assign dram_cke                = 'h0;
  assign dram_ras_n              = 'h1;
  assign dram_cas_n              = 'h1;
  assign dram_we_n               = 'h1;

  assign sram_a                  = 'h0;
  assign sram_dq                 = {16{1'bZ}};
  assign sram_oe_n               = 1;
  assign sram_we_n               = 1;
  assign sram_ub_n               = 1;
  assign sram_lb_n               = 1;

  assign dbg_tx                  = 1'bZ;
  assign user1                   = 1'bZ;
  assign aux_scl                 = 1'bZ;
  assign vpll_feed               = 1'bZ;


  // for bridge write data, we just broadcast it to all bus devices
  // for bridge read data, we have to mux it
  // add your own devices here
  always @(*) begin
    casex (bridge_addr)
      default: begin
        bridge_rd_data <= 0;
      end
      32'h10xxxxxx: begin
        // example
        // bridge_rd_data <= example_device_data;
        bridge_rd_data <= 0;
      end
      32'hF8xxxxxx: begin
        bridge_rd_data <= cmd_bridge_rd_data;
      end
    endcase
  end


  //
  // host/target command handler
  //
  wire reset_n;  // driven by host commands, can be used as core-wide reset
  wire [31:0] cmd_bridge_rd_data;

  // The PLL lives inside bosconian_pocket now, but its lock still gates the
  // status bits: core_bridge_cmd edge-detects status_setup_done to queue
  // READYTORUN, so it has to actually rise.
  wire pll_core_locked;
  wire pll_core_locked_s;
  synch_3 s01(pll_core_locked, pll_core_locked_s, clk_74a);

  // bridge host commands
  // synchronous to clk_74a
  wire status_boot_done = pll_core_locked_s;
  wire status_setup_done = pll_core_locked_s;  // rising edge triggers a target command
  wire status_running = reset_n;  // we are running as soon as reset_n goes high

  wire dataslot_requestread;
  wire [15:0] dataslot_requestread_id;
  wire dataslot_requestread_ack = 1;
  wire dataslot_requestread_ok = 1;

  wire dataslot_requestwrite;
  wire [15:0] dataslot_requestwrite_id;
  wire dataslot_requestwrite_ack = 1;
  wire dataslot_requestwrite_ok = 1;

  wire dataslot_allcomplete;

  wire savestate_supported;
  wire [31:0] savestate_addr;
  wire [31:0] savestate_size;
  wire [31:0] savestate_maxloadsize;

  wire savestate_start;
  wire savestate_start_ack;
  wire savestate_start_busy;
  wire savestate_start_ok;
  wire savestate_start_err;

  wire savestate_load;
  wire savestate_load_ack;
  wire savestate_load_busy;
  wire savestate_load_ok;
  wire savestate_load_err;

  wire osnotify_inmenu;

  // bridge target commands
  // synchronous to clk_74a


  // bridge data slot access

  wire [9:0] datatable_addr;
  wire datatable_wren;
  wire [31:0] datatable_data;
  wire [31:0] datatable_q;

  core_bridge_cmd icb (

      .clk    (clk_74a),
      .reset_n(reset_n),

      .bridge_endian_little(bridge_endian_little),
      .bridge_addr         (bridge_addr),
      .bridge_rd           (bridge_rd),
      .bridge_rd_data      (cmd_bridge_rd_data),
      .bridge_wr           (bridge_wr),
      .bridge_wr_data      (bridge_wr_data),

      .status_boot_done (status_boot_done),
      .status_setup_done(status_setup_done),
      .status_running   (status_running),

      .dataslot_requestread    (dataslot_requestread),
      .dataslot_requestread_id (dataslot_requestread_id),
      .dataslot_requestread_ack(dataslot_requestread_ack),
      .dataslot_requestread_ok (dataslot_requestread_ok),

      .dataslot_requestwrite    (dataslot_requestwrite),
      .dataslot_requestwrite_id (dataslot_requestwrite_id),
      .dataslot_requestwrite_ack(dataslot_requestwrite_ack),
      .dataslot_requestwrite_ok (dataslot_requestwrite_ok),

      .dataslot_allcomplete(dataslot_allcomplete),

      .savestate_supported  (savestate_supported),
      .savestate_addr       (savestate_addr),
      .savestate_size       (savestate_size),
      .savestate_maxloadsize(savestate_maxloadsize),

      .savestate_start     (savestate_start),
      .savestate_start_ack (savestate_start_ack),
      .savestate_start_busy(savestate_start_busy),
      .savestate_start_ok  (savestate_start_ok),
      .savestate_start_err (savestate_start_err),

      .savestate_load     (savestate_load),
      .savestate_load_ack (savestate_load_ack),
      .savestate_load_busy(savestate_load_busy),
      .savestate_load_ok  (savestate_load_ok),
      .savestate_load_err (savestate_load_err),

      .osnotify_inmenu(osnotify_inmenu),

      .datatable_addr(datatable_addr),
      .datatable_wren(datatable_wren),
      .datatable_data(datatable_data),
      .datatable_q   (datatable_q)
  );

  ////////////////////////////////////////////////////////////////////////////////////////


  // Bosconian core: clocks, video retiming, audio and inputs all live in
  // bosconian_pocket. This file stays the APF bridge adapter.
  wire [15:0] audio_l;
  wire [15:0] audio_r;

  // ROM streaming from dataslot 1.
  //
  // data_loader splits APF's 32-bit bridge writes into bytes in address
  // order, which is exactly the semantics rtl/bosconian.vhd already
  // expects from the MiSTer ioctl interface, so the core needs no change.
  //
  // clk_memory is clk_core (the core's own 18.432 MHz clock, exposed by
  // bosconian_pocket) rather than video_rgb_clock. data_loader holds
  // write_en high for exactly one clk_memory cycle; using the core clock
  // makes dn_wr a single-cycle pulse in the same domain the core samples
  // it in, matching MiSTer's ioctl_wr (driven from its own ~18 MHz
  // clk_sys, one cycle) instead of stretching the pulse across three core
  // cycles the way a slower clk_memory would.
  wire [15:0] dn_addr;
  wire  [7:0] dn_data;
  wire        dn_wr;
  wire        clk_core;

  // Held high from the first dataslot write until APF says every slot is
  // complete; bosconian_pocket ORs this into core_reset for the whole
  // transfer.
  reg dn_active = 0;
  always @(posedge clk_74a) begin
    if (dataslot_requestwrite) dn_active <= 1;
    else if (dataslot_allcomplete) dn_active <= 0;
  end

  data_loader #(
      .ADDRESS_MASK_UPPER_4(4'h0),
      .ADDRESS_SIZE(16),
      .OUTPUT_WORD_SIZE(1)
  ) rom_loader (
      .clk_74a   (clk_74a),
      .clk_memory(clk_core),

      .bridge_wr           (bridge_wr),
      .bridge_endian_little(bridge_endian_little),
      .bridge_addr         (bridge_addr),
      .bridge_wr_data      (bridge_wr_data),

      .write_en  (dn_wr),
      .write_addr(dn_addr),
      .write_data(dn_data)
  );

  // DIP switches, written by interact.json variables.
  //
  // One address per field: no read-modify-write masks to get wrong, and
  // each field can be tested independently on hardware. Values are held
  // in the MiSTer .mra polarity; bosconian_pocket inverts at the core
  // boundary, matching the MiSTer top level.
  //
  // Defaults reconstitute the .mra's default="08,68".
  reg [1:0] dsw_difficulty = 2'd0;
  reg       dsw_continue   = 1'b0;
  reg       dsw_demosound  = 1'b1;
  reg       dsw_freeze     = 1'b0;
  reg       dsw_cabinet    = 1'b0;
  reg [2:0] dsw_coinage    = 3'd0;
  reg [2:0] dsw_bonus      = 3'd5;
  reg [1:0] dsw_lives      = 2'd1;
  reg       dsw_selftest   = 1'b0;
  reg       dsw_service    = 1'b0;

  // reset_action must survive the crossing into bosconian_pocket's
  // clk_18432 domain (synch_3 there is a plain level synchroniser, not a
  // pulse-stretcher). bridge_wr is only one clk_74a cycle wide, and
  // clk_74a (74.25 MHz, 13.468 ns) is ~4x faster than clk_18432
  // (18.432 MHz, 54.257 ns), so a single-cycle pulse has only a
  // roughly-1-in-4 chance of being sampled. Stretch it with a down
  // counter instead: loading 5'd31 holds it for 31 clk_74a cycles
  // (31 * 13.468 ns = 417.5 ns = 7.7 clk_18432 periods), comfortably
  // more than the >=4 periods needed to guarantee a captured edge.
  // The counter self-clears to 0, so a menu reset can never leave the
  // core stuck in reset.
  reg [4:0] reset_hold = 0;
  wire reset_action = |reset_hold;

  always @(posedge clk_74a) begin
    if (bridge_wr && bridge_addr == 32'h10000000 && bridge_wr_data[0])
      reset_hold <= 5'd31;
    else if (reset_hold != 0)
      reset_hold <= reset_hold - 1'b1;

    if (bridge_wr) begin
      case (bridge_addr)
        32'h10020000: dsw_difficulty <= bridge_wr_data[1:0];
        32'h10020004: dsw_continue   <= bridge_wr_data[0];
        32'h10020008: dsw_demosound  <= bridge_wr_data[0];
        32'h1002000C: dsw_freeze     <= bridge_wr_data[0];
        32'h10020010: dsw_cabinet    <= bridge_wr_data[0];
        32'h10020014: dsw_coinage    <= bridge_wr_data[2:0];
        32'h10020018: dsw_bonus      <= bridge_wr_data[2:0];
        32'h1002001C: dsw_lives      <= bridge_wr_data[1:0];
        32'h10020020: dsw_selftest   <= bridge_wr_data[0];
        32'h10020024: dsw_service    <= bridge_wr_data[0];
        default: ;
      endcase
    end
  end

  wire [7:0] dip_a = {dsw_cabinet, 2'b00, dsw_freeze,
                      dsw_demosound, dsw_continue, dsw_difficulty};
  wire [7:0] dip_b = {dsw_lives, dsw_bonus, dsw_coinage};
  wire       self_test = dsw_selftest;
  wire       service = dsw_service;
  bosconian_pocket bc (
      .clk_74a(clk_74a),
      .reset_n(reset_n & ~reset_action),
      .dn_addr  (dn_addr),
      .dn_data  (dn_data),
      .dn_wr    (dn_wr),
      .dn_active(dn_active),
      .dip_a    (dip_a),
      .dip_b    (dip_b),
      .self_test(self_test),
      .service  (service),
      .cont1_key(cont1_key),
      .cont2_key(cont2_key),
      .video_rgb         (video_rgb),
      .video_de          (video_de),
      .video_hs          (video_hs),
      .video_vs          (video_vs),
      .video_skip        (video_skip),
      .video_rgb_clock   (video_rgb_clock),
      .video_rgb_clock_90(video_rgb_clock_90),
      .audio_l(audio_l),
      .audio_r(audio_r),
      .pll_locked(pll_core_locked),
      .clk_core  (clk_core)
  );
  ///////////////////////////////////////////////
  sound_i2s #(
      .CHANNEL_WIDTH(16),
      .SIGNED_INPUT (1)
  ) sound_i2s (
      .clk_74a  (clk_74a),
      .clk_audio(video_rgb_clock),
      .audio_l(audio_l),
      .audio_r(audio_r),
      .audio_mclk(audio_mclk),
      .audio_lrck(audio_lrck),
      .audio_dac (audio_dac)
  );


endmodule
