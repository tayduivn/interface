macro(TARGET_CRASHPAD)
    find_package(crashpad REQUIRED)
    target_link_libraries(${TARGET_NAME} crashpad crashpad::crashpad)

    if (WIN32)
        set(CRASHPAD_HANDLER_EXE_PATH "${crashpad_DIR}/../../tools/crashpad_handler.exe")
    else ()
        set(CRASHPAD_HANDLER_EXE_PATH "${crashpad_DIR}/../../tools/crashpad_handler")
    endif ()
endmacro()