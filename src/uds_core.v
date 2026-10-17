/*
 * UDS-1x1 voice engine. Bit-exact with model/uds_model.py (v0.2).
 *
 * All voice state is one shift register, the ring: N words of 48 bits that
 * move one bit per clock, so each voice passes the end of the ring once per
 * frame (48 x N clocks). While voice v's word passes, its envelope and phase
 * are updated bit-serially and written back into the start of the ring.
 *
 * Word layout, in the order the bits leave the ring:
 *   0-7 pitch, 8-11 decay, 12-15 sweep  (MSB first, as sent)
 *   16-23 env                           (LSB first)
 *   24-27 balance                       (MSB first, as sent)
 *   28-30 channel, 31 unused            (LSB first)
 *   32-47 phase                         (LSB first)
 *
 * Sound: no multiplier. On the last clock of window v-1 the engine reads
 * voice v's triangle, envelope and balance from the ring. During window v it
 * feeds 8 x signal to the sigma-delta on env>>3 clocks and 1 x signal on
 * env&7 clocks; on each of those clocks the signal is the triangle or the
 * noise, by a fixed pattern set by the balance. The DAC is a second-order
 * 1-bit sigma-delta (see the end of the file).
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module uds_core #(
    parameter N        = 4,         // voices
    parameter TRIGGERS = 1,         // 1: pin triggers on trig[7:0]
    parameter STATUS   = 1          // 1: per-channel STATUS register
) (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        hit_done,
    input  wire        stop,
    input  wire [2:0]  hit_ch,
    input  wire        payload_msb,
    input  wire [3:0]  level,
    input  wire        spi_idle,
    output wire        commit_shift,
    output wire        preset_load,
    output reg  [2:0]  preset_ch,
    output reg  [23:0] preset,

    input  wire [7:0]  trig,        // pin triggers, one per channel
    output reg  [7:0]  status,      // channels sounding, latched once per frame
    output wire        audio,       // sigma-delta output (second order)
    output wire        busy,        // a HIT is waiting or being written
    output wire        frame_sync   // high during voice window 0
);

  localparam L  = 48;
  localparam NL = N * L;
  localparam VW = (N > 2) ? $clog2(N) : 1;

  // ------------------------------------------------------------------ timing
  reg  [5:0]    t;                  // clock within the voice window, 0..47
  reg  [VW-1:0] v;                  // voice window, 0..N-1
  reg  [12:0]   frame;              // decay up to 13: 2^13 frames per step
  reg           clearing;           // first frame after reset: fill the ring with 0
  wire          wend = t == 6'd47;
  wire          fend = wend && v == N - 1;

  always @(posedge clk) begin
    if (!rst_n) begin
      t        <= 6'd0;
      v        <= {VW{1'b0}};
      frame    <= 13'd0;
      clearing <= 1'b1;
    end else begin
      t <= wend ? 6'd0 : t + 6'd1;
      if (wend) v <= (v == N - 1) ? {VW{1'b0}} : v + 1'b1;
      if (fend) begin
        frame    <= frame + 13'd1;
        clearing <= 1'b0;
      end
    end
  end

  // -------------------------------------------------------------------- ring
  reg  [NL-1:0] ring;
  reg           tail;
  wire          head = ring[NL-1];

  always @(posedge clk) ring <= {ring[NL-2:0], tail};

  // On the last clock of a window, word bit b of the next voice is ring[NL-2-b].
  wire [L-1:0] nw;
  genvar gb;
  generate
    for (gb = 0; gb < L; gb = gb + 1) begin : g_next_word
      assign nw[gb] = ring[NL-2-gb];
    end
  endgenerate

  wire [7:0] n_pitch = {nw[0], nw[1], nw[2], nw[3], nw[4], nw[5], nw[6], nw[7]};
  wire [3:0] n_sweep = {nw[12], nw[13], nw[14], nw[15]};
  wire [3:0] n_bal   = {nw[24], nw[25], nw[26], nw[27]};
  wire [7:0] n_env   = nw[23:16];
  wire [9:0] n_ph    = nw[47:38];                    // phase[15:6]
  wire [2:0] n_ch    = nw[30:28];

  // effective pitch: pitch + sweep offset, at most 255 (sweep bit 3 is reserved)
  wire [6:0] up     = n_env[7] ? n_env[6:0] : 7'd0;
  wire [6:0] off    = up >> (3'd7 - n_sweep[2:0]);
  wire [8:0] pe_raw = {1'b0, n_pitch} + {2'b00, off};
  wire [7:0] n_pe   = pe_raw[8] ? 8'd255 : pe_raw[7:0];

  // triangle: fold phase[15:6] around phase[15], 9 bits signed
  wire [8:0] fold   = n_ph[8:0] ^ {9{n_ph[9]}};
  wire [8:0] n_tri  = {~fold[8], fold[7:0]};

  // ---------------------------------------------- per-window captured values
  reg [8:0] c_tri;
  reg [7:0] c_env;
  reg [3:0] c_bal;
  reg       c_metal;
  reg [7:0] c_pe;
  reg       c_dec;                  // envelope steps this frame

  // decay is read on clock 0 of the window, when word bit b is ring[NL-1-b]
  wire [3:0]  c0_decay = {ring[NL-9], ring[NL-10], ring[NL-11], ring[NL-12]};
  wire [12:0] dmask    = ~(13'h1FFF << c0_decay);  // decay 13..15 act as 13

  always @(posedge clk) begin
    if (wend) begin
      c_tri   <= n_tri;
      c_env   <= n_env;
      c_bal   <= n_bal;
      c_metal <= n_ch[2] & (n_ch[1] | n_ch[0]);
      c_pe    <= n_pe;
    end
    if (t == 6'd0) c_dec <= (|c_env) & ~|(frame & dmask);
  end

  // ------------------------------------------------- bit-serial env and phase
  wire       in_env   = t[5:3] == 3'b010;            // 16..23
  wire       in_phase = t[5:4] == 2'b10;             // 32..47
  wire [2:0] ej       = t[2:0];                      // env bit
  wire [3:0] pj       = t[3:0];                      // phase bit

  // env -= max(env >> 3, 1); bit j of env >> 3 is 3 bits ahead in the ring
  reg        bor;
  wire       env_lt8 = c_env[7:3] == 5'd0;
  wire       d_bit   = env_lt8 ? (ej == 3'd0) : (ring[NL-4] & (ej <= 3'd4));
  wire       bor_in  = (ej == 3'd0) ? 1'b0 : bor;
  wire       env_new = head ^ d_bit ^ bor_in;

  // phase += (32 + pe[4:0]) << pe[7:5]
  reg        cy;
  wire [4:0] pk      = {1'b0, pj} - {2'b00, c_pe[7:5]};
  wire [5:0] mant    = {1'b1, c_pe[4:0]};
  wire       inc_bit = !pk[4] && pk[3:0] <= 4'd5 && mant[pk[2:0]];
  wire       cy_in   = (pj == 4'd0) ? 1'b0 : cy;
  wire       ph_new  = head ^ inc_bit ^ cy_in;

  always @(posedge clk) begin
    bor <= (~head & (d_bit | bor_in)) | (d_bit & bor_in);
    cy  <= (head & inc_bit) | (head & cy_in) | (inc_bit & cy_in);
  end

  // ------------------------------------------------------- HITs and commits
  reg          pend;                // a HIT waits for the next frame boundary
  reg          commit;              // this frame writes the new word into slot tgt
  reg  [VW-1:0] tgt;
  reg          kill, kill_pend;
  reg  [VW-1:0] choice;
  wire         committing = commit && v == tgt;
  reg          tail_commit;

  assign commit_shift = committing && (t[5:4] == 2'b00 || t[5:2] == 4'b0110);  // 0..15, 24..27
  assign busy         = pend | commit;
  assign frame_sync   = v == {VW{1'b0}};

  always @(*) begin
    case (t[5:3])
      3'd0, 3'd1: tail_commit = payload_msb;                  // pitch, decay, sweep
      3'd2:       tail_commit = level[ej[1:0]];               // env = 17 x level
      3'd3:       tail_commit = t[2] ? (!(&t[1:0]) && hit_ch[t[1:0]])  // channel, unused
                                     : payload_msb;           // balance
      default:    tail_commit = t[3:0] == 4'd14;              // phase = 0x4000
    endcase
  end

  always @(*) begin
    if (clearing)        tail = 1'b0;
    else if (committing) tail = tail_commit;
    else if (in_env)     tail = !kill && (c_dec ? env_new : head);
    else if (in_phase)   tail = ph_new;
    else                 tail = head;
  end

  // ------------------------------------------------- slot choice and status
  // On the last clock of a frame, voice u's word bit b is ring[NL-2-u*L-b].
  wire [N-1:0]   act, same;
  wire [3*N-1:0] envhi;
  wire [8*N-1:0] chbits;
  wire [2:0]     hgrp = (hit_ch == 3'd7) ? 3'd6 : hit_ch;
  genvar gu, gk;
  generate
    for (gu = 0; gu < N; gu = gu + 1) begin : g_slot
      wire [7:0] e;
      wire [2:0] c;
      for (gk = 0; gk < 8; gk = gk + 1) begin : g_env
        assign e[gk] = ring[NL-2-gu*L-16-gk];
      end
      for (gk = 0; gk < 3; gk = gk + 1) begin : g_ch
        assign c[gk] = ring[NL-2-gu*L-28-gk];
      end
      assign act[gu]            = |e;
      assign same[gu]           = act[gu] && ((c == 3'd7) ? 3'd6 : c) == hgrp;
      assign envhi[3*gu +: 3]   = e[7:5];
      assign chbits[8*gu +: 8]  = act[gu] ? (8'd1 << c) : 8'd0;
    end
  endgenerate

  integer i;
  reg [2:0] best;
  reg [7:0] status_next;
  always @(*) begin
    choice = {VW{1'b0}};                      // quietest, lowest index on ties
    best   = envhi[2:0];
    for (i = 1; i < N; i = i + 1)
      if (envhi[3*i +: 3] < best) begin
        best   = envhi[3*i +: 3];
        choice = i[VW-1:0];
      end
    for (i = N - 1; i >= 0; i = i - 1)        // a free slot beats stealing
      if (!act[i]) choice = i[VW-1:0];
    for (i = N - 1; i >= 0; i = i - 1)        // the same drum beats both
      if (same[i]) choice = i[VW-1:0];
    status_next = 8'd0;
    for (i = 0; i < N; i = i + 1)
      status_next = status_next | chbits[8*i +: 8];
  end

  // ------------------------------------------------------------ pin triggers
  reg  [7:0] trig_s, served;
  wire [7:0] waiting  = trig_s & ~served;
  wire [7:0] first    = waiting & (~waiting + 8'd1);      // lowest waiting pin
  assign preset_load  = TRIGGERS != 0 && fend && !pend && spi_idle && |waiting;

  always @(*) begin
    case (first)
      8'h01:   preset_ch = 3'd0;
      8'h02:   preset_ch = 3'd1;
      8'h04:   preset_ch = 3'd2;
      8'h08:   preset_ch = 3'd3;
      8'h10:   preset_ch = 3'd4;
      8'h20:   preset_ch = 3'd5;
      8'h40:   preset_ch = 3'd6;
      default: preset_ch = 3'd7;
    endcase
    // pitch, decay<<4 | sweep, balance<<4 | level (model PRESETS)
    case (preset_ch)
      3'd0:    preset = 24'h50_74_BD;   // snare
      3'd1:    preset = 24'h54_85_2C;   // small tom
      3'd2:    preset = 24'h46_85_2C;   // middle tom
      3'd3:    preset = 24'h38_95_2C;   // big tom
      3'd4:    preset = 24'h14_96_1F;   // bass drum
      3'd5:    preset = 24'hFF_B0_FB;   // cymbal
      3'd6:    preset = 24'hFF_60_FA;   // closed hi-hat
      default: preset = 24'hFF_90_FA;   // open hi-hat
    endcase
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      pend      <= 1'b0;
      commit    <= 1'b0;
      kill      <= 1'b0;
      kill_pend <= 1'b0;
      trig_s    <= 8'd0;
      served    <= 8'd0;
      status    <= 8'd0;
    end else begin
      trig_s    <= TRIGGERS != 0 ? trig : 8'd0;
      served    <= (served | (preset_load ? first : 8'd0)) & trig_s;
      pend      <= hit_done | preset_load | (pend & !fend);
      kill_pend <= stop | (kill_pend & !fend);
      if (fend) begin
        commit <= pend;
        kill   <= kill_pend;
        status <= STATUS != 0 ? status_next : 8'd0;
      end
    end
    if (fend && pend) tgt <= choice;
  end

  // ------------------------------------------------------------ noise sources
  reg [16:0] lfsr;
  reg [1:0]  m3;
  reg [2:0]  m5, m7;
  reg        sq3, sq5, sq7;

  always @(posedge clk) begin
    if (!rst_n) begin
      lfsr <= 17'd1;
      m3 <= 2'd0; m5 <= 3'd0; m7 <= 3'd0;
      sq3 <= 1'b0; sq5 <= 1'b0; sq7 <= 1'b0;
    end else if (fend) begin
      lfsr <= {lfsr[15:0], lfsr[16] ^ lfsr[13]};
      if (m3 == 2'd2) begin m3 <= 2'd0; sq3 <= ~sq3; end else m3 <= m3 + 2'd1;
      if (m5 == 3'd4) begin m5 <= 3'd0; sq5 <= ~sq5; end else m5 <= m5 + 3'd1;
      if (m7 == 3'd6) begin m7 <= 3'd0; sq7 <= ~sq7; end else m7 <= m7 + 3'd1;
    end
  end

  wire [2:0] pc    = {2'b00, lfsr[0]} + {2'b00, lfsr[1]} + {2'b00, lfsr[2]} + {2'b00, lfsr[3]};
  wire [8:0] drum  = pc[2] ? 9'h0FF : {~pc[1], pc[0], 7'd0};   // popcount x 128 - 256
  wire [8:0] metal = (sq3 ^ sq5 ^ sq7 ^ frame[2]) ? 9'h0FF : 9'h100;

  // ------------------------------------------------------------- sigma-delta
  // Second-order 1-bit loop, two delaying integrators, noise transfer
  // function (1 - z^-1)^2, input at half scale (model: Engine.dac2):
  //   y   = v2 >= 0                    the pin, one clock after the update
  //   fb  = y ? +4096 : -4096
  //   v1 <= clamp(v1 + x - fb)         15 bits, saturating (a safety net only)
  //   v2 <= v2 + v1 - 2 fb             17 bits: -45056 <= v2 <= 45050 for any
  //                                    |x| <= 2048 (sd2_bounds() in the model)
  // Both adders take registered values, so they work side by side.
  wire [4:0]  q     = c_env[7:3];
  wire [5:0]  qr    = {1'b0, q} + {3'b000, c_env[2:0]};
  wire        w8    = t < {1'b0, q};
  wire        w1    = !w8 && t < qr;
  wire        sel_n = {t[0], t[1], t[2], t[3]} < c_bal;
  wire [8:0]  src   = sel_n ? (c_metal ? metal : drum) : c_tri;
  wire [11:0] x     = clearing ? 12'd0 :
                      w8 ? {src, 3'b000} :
                      w1 ? {{3{src[8]}}, src} : 12'd0;

  reg  [14:0] sd_v1;
  reg  [16:0] sd_v2;
  wire        y     = ~sd_v2[16];
  // x - fb in 16 bits, no logic: x is in [-2048, 2047], so x -/+ 4096 only
  // changes the bits above bit 11
  wire [15:0] x_fb  = {{3{y}}, ~x[11], x};
  wire [15:0] s1    = {sd_v1[14], sd_v1} + x_fb;
  wire        ovf1  = s1[15] ^ s1[14];
  wire [14:0] v1_n  = ovf1 ? {s1[15], {14{~s1[15]}}} : s1[14:0];
  wire [16:0] v2_n  = sd_v2 + {{2{sd_v1[14]}}, sd_v1} + {{3{y}}, 1'b1, 13'd0};   // + v1 - 2 fb

  // When no voice sounds at the end of a frame, the next frame is silent:
  // restart the loop on the frame's last clock (its x is always 0), so that
  // every silence is the same clean 0110 pattern, 48 ones per frame.
  wire        sd_restart = !rst_n || (fend && !(|act));

  always @(posedge clk) begin
    if (sd_restart) begin
      sd_v1 <= 15'd0;
      sd_v2 <= {17{1'b1}};          // -1: the pin is low in reset
    end else begin
      sd_v1 <= v1_n;
      sd_v2 <= v2_n;
    end
  end

  assign audio = y;

endmodule
