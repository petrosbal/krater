;; matrix_mult inlined into $main at -O3
;; benchmark measurement loop: C[] zero-init + i/k/j multiply-accumulate
;; extracted from $main in bench_o3.wasm
;; lines 486-676 of WAT
;; bench_o3.wasm is byte-identical to bench_o2.wasm, verified via sha256sum

          local.get 4
          i32.const 3
          i32.shl
          local.set 16
          local.get 4
          i32.const 2147483646
          i32.and
          local.set 12
          local.get 4
          i32.const 1
          i32.and
          local.set 17
          i32.const 0
          local.set 23
          loop  ;; label = @4
            block  ;; label = @5
              local.get 7
              i32.eqz
              br_if 0 (;@5;)
              local.get 10
              i32.const 0
              local.get 7
              memory.fill
            end
            local.get 10
            local.set 18
            i32.const 0
            local.set 19
            loop  ;; label = @5
              local.get 10
              local.get 19
              local.get 4
              i32.mul
              i32.const 3
              i32.shl
              local.tee 1
              i32.add
              local.set 20
              local.get 8
              local.get 1
              i32.add
              local.set 21
              i32.const 0
              local.set 13
              local.get 9
              local.set 3
              loop  ;; label = @6
                local.get 21
                local.get 13
                i32.const 3
                i32.shl
                i32.add
                f64.load
                local.set 22
                i32.const 0
                local.set 14
                block  ;; label = @7
                  block  ;; label = @8
                    local.get 4
                    i32.const 1
                    i32.eq
                    br_if 0 (;@8;)
                    i32.const 0
                    local.set 14
                    local.get 18
                    local.set 1
                    local.get 3
                    local.set 0
                    loop  ;; label = @9
                      local.get 1
                      local.get 22
                      local.get 0
                      f64.load
                      f64.mul
                      local.get 1
                      f64.load
                      f64.add
                      f64.store
                      local.get 1
                      i32.const 8
                      i32.add
                      local.tee 11
                      local.get 22
                      local.get 0
                      i32.const 8
                      i32.add
                      f64.load
                      f64.mul
                      local.get 11
                      f64.load
                      f64.add
                      f64.store
                      local.get 1
                      i32.const 16
                      i32.add
                      local.set 1
                      local.get 0
                      i32.const 16
                      i32.add
                      local.set 0
                      local.get 12
                      local.get 14
                      i32.const 2
                      i32.add
                      local.tee 14
                      i32.ne
                      br_if 0 (;@9;)
                    end
                    local.get 17
                    i32.eqz
                    br_if 1 (;@7;)
                  end
                  local.get 20
                  local.get 14
                  i32.const 3
                  i32.shl
                  local.tee 1
                  i32.add
                  local.tee 0
                  local.get 22
                  local.get 9
                  local.get 13
                  local.get 4
                  i32.mul
                  i32.const 3
                  i32.shl
                  i32.add
                  local.get 1
                  i32.add
                  f64.load
                  f64.mul
                  local.get 0
                  f64.load
                  f64.add
                  f64.store
                end
                local.get 3
                local.get 16
                i32.add
                local.set 3
                local.get 13
                i32.const 1
                i32.add
                local.tee 13
                local.get 4
                i32.ne
                br_if 0 (;@6;)
              end
              local.get 18
              local.get 16
              i32.add
              local.set 18
              local.get 19
              i32.const 1
              i32.add
              local.tee 19
              local.get 4
              i32.ne
              br_if 0 (;@5;)
            end
            local.get 2
            i32.const 96
            i32.add
            i32.const 1
            call $timespec_get
            drop
            local.get 23
            i32.const 1
            i32.add
            local.set 23
            local.get 2
            i32.load offset=104
            local.get 2
            i32.load offset=120
            i32.sub
            f64.convert_i32_s
            f64.const 0x1.dcd65p+29 (;=1e+09;)
            f64.div
            local.get 2
            i64.load offset=96
            local.get 2
            i64.load offset=112
            i64.sub
            f64.convert_i64_s
            f64.add
            local.tee 22
            local.get 5
            f64.lt
            br_if 0 (;@4;)
          end
        end
