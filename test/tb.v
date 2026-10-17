`default_nettype none
`timescale 1ns / 1ps

/* Testbench for UDS-1x1. Besides the usual wiring it counts the 1s on the
   audio pin in every frame, so the cocotb test can compare each frame with
   the Python model (model/uds_model.py) without sampling every clock.
*/
module tb ();

  // Dump the signals to a FST file. You can view it with gtkwave or surfer.
  initial begin
    $dumpfile("tb.fst");
    $dumpvars(1, tb);
    #1;
  end

  // Clocks per frame = 48 x voices. Must match VOICES in src/project.v.
  parameter FRAME = 192;

  // Wire up the inputs and outputs:
  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;
`ifdef GL_TEST
  wire VPWR = 1'b1;
  wire VGND = 1'b0;
`endif

  tt_um_ai_wrangler_uds1x1 user_project (

      // Include power ports for the Gate Level test:
`ifdef GL_TEST
      .VPWR(VPWR),
      .VGND(VGND),
`endif

      .ui_in  (ui_in),    // Dedicated inputs
      .uo_out (uo_out),   // Dedicated outputs
      .uio_in (uio_in),   // IOs: Input path
      .uio_out(uio_out),  // IOs: Output path
      .uio_oe (uio_oe),   // IOs: Enable path (active high: 0=input, 1=output)
      .ena    (ena),      // enable - goes high when design is selected
      .clk    (clk),      // clock
      .rst_n  (rst_n)     // not reset
  );

  // cyc = clock within the run; frame clock 0 is the cycle that ends with the
  // first rising edge after reset, the same as the chip's own counters.
  // The audio pin in cycle c carries the sigma-delta carry of cycle c - 1, so
  // frame k is the samples taken at the ends of cycles k*FRAME+1 .. (k+1)*FRAME.
  reg [31:0] cyc;
  reg [15:0] ones_acc;
  reg [15:0] frame_ones;    // 1s in the last complete frame
  reg [31:0] frame_count;   // complete frames since reset
  reg        frame_tick;    // toggles when a frame completes

  always @(posedge clk) begin
    if (!rst_n) begin
      cyc         <= 32'd0;
      ones_acc    <= 16'd0;
      frame_ones  <= 16'd0;
      frame_count <= 32'd0;
      frame_tick  <= 1'b0;
    end else begin
      cyc <= cyc + 32'd1;
      if (cyc != 32'd0 && cyc % FRAME == 0) begin
        frame_ones  <= ones_acc + {15'd0, uo_out[7]};
        ones_acc    <= 16'd0;
        frame_count <= frame_count + 32'd1;
        frame_tick  <= ~frame_tick;
      end else if (cyc != 32'd0) begin
        ones_acc <= ones_acc + {15'd0, uo_out[7]};
      end
    end
  end

endmodule
