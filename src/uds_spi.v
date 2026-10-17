/*
 * UDS-1x1: SPI receiver (mode 0, MSB first) and the 24-bit HIT payload register.
 *
 * Messages (CS low for the whole message):
 *   HIT   0x18|ch, pitch, decay<<4|sweep, balance<<4|level
 *   READ  0x30|reg, then one byte clocked out on MISO (0 ID, 1 VERSION, 2 STATUS)
 *   STOP  0x40
 * SCK and CS are oversampled by clk: keep SCK at or below clk/6.
 *
 * The payload register is shared with the voice engine: a commit shifts it
 * out MSB first into the voice ring, and a pin trigger loads a preset into it.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module uds_spi #(
    parameter [7:0] CHIP_ID     = 8'hD5,
    parameter [7:0] VERSION_REG = 8'h14
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        cs_n_pin,
    input  wire        sck_pin,
    input  wire        mosi_pin,
    output wire        miso,
    output wire        idle,          // CS is high
    input  wire [7:0]  status,

    output wire        hit_done,      // one-clock pulse: the last bit of a HIT arrived
    output wire        stop,          // one-clock pulse: STOP
    output reg  [2:0]  ch,            // channel of the HIT (or of the pin trigger)
    output wire        payload_msb,   // sr[23]
    output wire [3:0]  level,         // sr[19:16]: the level nibble after 16 shifts

    input  wire        commit_shift,  // voice engine: shift the payload out
    input  wire        preset_load,   // voice engine: load a pin trigger preset
    input  wire [2:0]  preset_ch,
    input  wire [23:0] preset
);

  reg [1:0] cs_s;       // synchronizer; cs_s[1] is the CS level
  reg [2:0] sck_s;      // synchronizer; [1] is the SCK level, [2] the previous one
  reg       mosi_s;
  reg [2:0] bitcnt;
  reg [1:0] bytecnt;    // 0 = command byte, then 1..3 (stays at 3)
  reg       is_hit;
  reg [23:0] sr;

  wire       active   = !cs_s[1];
  wire       rise     = active && sck_s[1] && !sck_s[2];
  wire [7:0] byte_in  = {sr[6:0], mosi_s};
  wire       cmd_end  = rise && bitcnt == 3'd7 && bytecnt == 2'd0;
  wire       read_cmd = byte_in[7:4] == 4'h3;

  reg  [7:0] read_value;
  always @(*) begin
    case (byte_in[1:0])
      2'd0:    read_value = CHIP_ID;
      2'd1:    read_value = VERSION_REG;
      2'd2:    read_value = status;
      default: read_value = 8'h00;
    endcase
  end

  assign hit_done    = rise && bitcnt == 3'd7 && bytecnt == 2'd3 && is_hit;
  assign stop        = cmd_end && byte_in == 8'h40;
  assign idle        = cs_s[1];
  assign miso        = active & sr[7];
  assign payload_msb = sr[23];
  assign level       = sr[19:16];

  always @(posedge clk) begin
    mosi_s   <= mosi_pin;
    if (!rst_n) begin
      cs_s    <= 2'b11;
      sck_s   <= 3'b000;
      bitcnt  <= 3'd0;
      bytecnt <= 2'd0;
      is_hit  <= 1'b0;
    end else begin
      cs_s  <= {cs_s[0], cs_n_pin};
      sck_s <= {sck_s[1:0], sck_pin};
      if (!active) begin
        bitcnt  <= 3'd0;
        bytecnt <= 2'd0;
        is_hit  <= 1'b0;
      end else if (rise) begin
        bitcnt <= bitcnt + 3'd1;
        if (bitcnt == 3'd7) begin
          if (bytecnt != 2'd3) bytecnt <= bytecnt + 2'd1;
          if (bytecnt == 2'd0) is_hit <= byte_in[7:3] == 5'b00011;
          if (bytecnt == 2'd3) is_hit <= 1'b0;
        end
      end
    end
  end

  // Channel register: from the HIT command byte, or from a pin trigger.
  always @(posedge clk) begin
    if (!rst_n) ch <= 3'd0;
    else if (preset_load) ch <= preset_ch;
    else if (cmd_end && byte_in[7:3] == 5'b00011) ch <= byte_in[2:0];
  end

  // Shift register: SPI bits in, commit bits out, preset load, READ answer.
  always @(posedge clk) begin
    if (preset_load) sr <= preset;
    else if (commit_shift) sr <= {sr[22:0], 1'b0};
    else if (rise) begin
      sr <= {sr[22:0], mosi_s};
      if (cmd_end && read_cmd) sr[7:0] <= read_value;   // answer goes out on the next byte
    end
  end

endmodule
