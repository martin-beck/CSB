# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.22)

project(
    CSB-Generator
    LANGUAGES C
    DESCRIPTION "Benchmark Generator of CSB")

include(FetchContent)

message(STATUS "Fetching syzkaller ...")

FetchContent_Declare(
  syzkaller
  GIT_REPOSITORY https://github.com/martin-beck/syzkaller.git
  GIT_TAG a4eebe883f3a0fff811fc76061671b174820fcf6
  GIT_PROGRESS TRUE
)
FetchContent_MakeAvailable(syzkaller)

FetchContent_GetProperties(syzkaller
  SOURCE_DIR syzkaller_SOURCE_DIR
)

find_program(GO_EXECUTABLE go)
if(NOT GO_EXECUTABLE)
    message(FATAL_ERROR "Go compiler not found. Please install Go.")
endif()
message(STATUS "Go found at: ${GO_EXECUTABLE}")

# build syzkaller
add_custom_target(syzkaller ALL
    COMMAND make
    WORKING_DIRECTORY ${syzkaller_SOURCE_DIR}
)

set(TOOLS_DIR "${syzkaller_SOURCE_DIR}/tools")
# Tools we want to build of syzkaller
set(TOOLS trace2syz prog2c extraction)
# Build each tool
foreach(TOOL IN ITEMS ${TOOLS})
    set(TOOL_NAME syz-${TOOL})
    message(STATUS "Building syzkaller tool: ${TOOL_NAME}")
    add_custom_target(${TOOL} ALL
        COMMAND go build
        WORKING_DIRECTORY "${TOOLS_DIR}/${TOOL_NAME}"
    )
endforeach(TOOL in ${TOOLS})

# Save syzkaller path to a file.
file(WRITE "${CMAKE_BINARY_DIR}/syzkaller-path.txt" "${syzkaller_SOURCE_DIR}")

add_subdirectory(templates)

