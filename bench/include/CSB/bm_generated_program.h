/*
 * Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
 * SPDX-License-Identifier: MIT
 */
#ifndef BM_GENERATED_PROGRAM_H
#define BM_GENERATED_PROGRAM_H

#include <stddef.h>
#include <stdint.h>

typedef struct csb_program_result_s {
  uint64_t op_count;
  uint64_t succ_count;
} csb_program_result_t;

typedef struct csb_generated_program_s {
  const char *name;
  void (*init)(uint16_t port);
  void *(*create)(size_t tid);
  csb_program_result_t (*dispatch)(void *state, size_t op_id);
  void (*destroy)(void *state);
} csb_generated_program_t;

#endif
