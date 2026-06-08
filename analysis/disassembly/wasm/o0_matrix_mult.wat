  (func $matrix_mult (type 9) (param i32 i32 i32 i32)
    (local i32 f64 f64 i32)
    global.get $__stack_pointer
    i32.const 48
    i32.sub
    local.set 4
    local.get 4
    local.get 0
    i32.store offset=44
    local.get 4
    local.get 1
    i32.store offset=40
    local.get 4
    local.get 2
    i32.store offset=36
    local.get 4
    local.get 3
    i32.store offset=32
    local.get 4
    i32.const 0
    i32.store offset=28
    block  ;; label = @1
      loop  ;; label = @2
        local.get 4
        i32.load offset=28
        local.get 4
        i32.load offset=32
        local.get 4
        i32.load offset=32
        i32.mul
        i32.lt_s
        i32.const 1
        i32.and
        i32.eqz
        br_if 1 (;@1;)
        local.get 4
        i32.load offset=36
        local.get 4
        i32.load offset=28
        i32.const 3
        i32.shl
        i32.add
        i32.const 0
        f64.convert_i32_s
        f64.store
        local.get 4
        local.get 4
        i32.load offset=28
        i32.const 1
        i32.add
        i32.store offset=28
        br 0 (;@2;)
      end
    end
    local.get 4
    i32.const 0
    i32.store offset=24
    block  ;; label = @1
      loop  ;; label = @2
        local.get 4
        i32.load offset=24
        local.get 4
        i32.load offset=32
        i32.lt_s
        i32.const 1
        i32.and
        i32.eqz
        br_if 1 (;@1;)
        local.get 4
        i32.const 0
        i32.store offset=20
        block  ;; label = @3
          loop  ;; label = @4
            local.get 4
            i32.load offset=20
            local.get 4
            i32.load offset=32
            i32.lt_s
            i32.const 1
            i32.and
            i32.eqz
            br_if 1 (;@3;)
            local.get 4
            local.get 4
            i32.load offset=44
            local.get 4
            i32.load offset=24
            local.get 4
            i32.load offset=32
            i32.mul
            local.get 4
            i32.load offset=20
            i32.add
            i32.const 3
            i32.shl
            i32.add
            f64.load
            f64.store offset=8
            local.get 4
            i32.const 0
            i32.store offset=4
            block  ;; label = @5
              loop  ;; label = @6
                local.get 4
                i32.load offset=4
                local.get 4
                i32.load offset=32
                i32.lt_s
                i32.const 1
                i32.and
                i32.eqz
                br_if 1 (;@5;)
                local.get 4
                f64.load offset=8
                local.set 5
                local.get 4
                i32.load offset=40
                local.get 4
                i32.load offset=20
                local.get 4
                i32.load offset=32
                i32.mul
                local.get 4
                i32.load offset=4
                i32.add
                i32.const 3
                i32.shl
                i32.add
                f64.load
                local.set 6
                local.get 4
                i32.load offset=36
                local.get 4
                i32.load offset=24
                local.get 4
                i32.load offset=32
                i32.mul
                local.get 4
                i32.load offset=4
                i32.add
                i32.const 3
                i32.shl
                i32.add
                local.set 7
                local.get 7
                local.get 7
                f64.load
                local.get 5
                local.get 6
                f64.mul
                f64.add
                f64.store
                local.get 4
                local.get 4
                i32.load offset=4
                i32.const 1
                i32.add
                i32.store offset=4
                br 0 (;@6;)
              end
            end
            local.get 4
            local.get 4
            i32.load offset=20
            i32.const 1
            i32.add
            i32.store offset=20
            br 0 (;@4;)
          end
        end
        local.get 4
        local.get 4
        i32.load offset=24
        i32.const 1
        i32.add
        i32.store offset=24
        br 0 (;@2;)
      end
    end
    return)
