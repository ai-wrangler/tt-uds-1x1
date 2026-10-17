/*
 * UDS-1x1: a digital homage to the Formanta UDS drum synthesizer.
 * Copyright (c) 2026 Juris Vitols
 * SPDX-License-Identifier: Apache-2.0
 *
 * ui_in[7:0]   pin triggers (if TRIGGERS): a rising edge plays channel 0..7 with its preset
 * uo_out[6:0]  7-segment display: with STATUS, segments light while their drum sounds;
 *              without, the digit of the channel last hit
 * uo_out[7]    audio (sigma-delta bitstream, low-pass filter it)
 * uio[0] CS_N in, uio[1] MOSI in, uio[2] MISO out, uio[3] SCK in
 * uio[4] FRAME out (high during voice window 0), uio[5] BUSY out
 * uio[6] audio out (left), uio[7] audio out (right): same signal, the chip is mono
 */
`default_nettype none

module tt_um_ai_wrangler_uds1x1 (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // Build options. 1x1 tile: 2 voices, no pin triggers, no STATUS (run at 6 MHz).
  localparam [3:0] VOICES   = 4'd2;
  localparam       TRIGGERS = 0;
  localparam       STATUS   = 0;

  wire        miso, spi_idle, hit_done, stop, payload_msb;
  wire        commit_shift, preset_load;
  wire [2:0]  hit_ch, preset_ch;
  wire [3:0]  level;
  wire [23:0] preset;
  wire [7:0]  status;
  wire        audio, busy, frame_sync;

  uds_spi #(
      .CHIP_ID    (8'hD5),
      .VERSION_REG({4'd1, VOICES})
  ) spi (
      .clk         (clk),
      .rst_n       (rst_n),
      .cs_n_pin    (uio_in[0]),
      .sck_pin     (uio_in[3]),
      .mosi_pin    (uio_in[1]),
      .miso        (miso),
      .idle        (spi_idle),
      .status      (status),
      .hit_done    (hit_done),
      .stop        (stop),
      .ch          (hit_ch),
      .payload_msb (payload_msb),
      .level       (level),
      .commit_shift(commit_shift),
      .preset_load (preset_load),
      .preset_ch   (preset_ch),
      .preset      (preset)
  );

  uds_core #(
      .N       (VOICES),
      .TRIGGERS(TRIGGERS),
      .STATUS  (STATUS)
  ) core (
      .clk         (clk),
      .rst_n       (rst_n),
      .hit_done    (hit_done),
      .stop        (stop),
      .hit_ch      (hit_ch),
      .payload_msb (payload_msb),
      .level       (level),
      .spi_idle    (spi_idle),
      .commit_shift(commit_shift),
      .preset_load (preset_load),
      .preset_ch   (preset_ch),
      .preset      (preset),
      .trig        (ui_in),
      .status      (status),
      .audio       (audio),
      .busy        (busy),
      .frame_sync  (frame_sync)
  );

  reg [6:0] digit;
  always @(*) begin
    case (hit_ch)
      3'd0:    digit = 7'h3F;
      3'd1:    digit = 7'h06;
      3'd2:    digit = 7'h5B;
      3'd3:    digit = 7'h4F;
      3'd4:    digit = 7'h66;
      3'd5:    digit = 7'h6D;
      3'd6:    digit = 7'h7D;
      default: digit = 7'h07;
    endcase
  end

  assign uo_out  = {audio, STATUS != 0 ? {status[6] | status[7], status[5:0]} : digit};
  assign uio_out = {audio, audio, busy, frame_sync, 1'b0, miso, 2'b00};
  assign uio_oe  = 8'b1111_0100;

  wire _unused = &{ena, uio_in[7:4], uio_in[2], 1'b0};

endmodule
