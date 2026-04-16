set(srcs "main.cpp")

idf_component_register(SRCS ${srcs}
                    INCLUDE_DIRS "."
                    REQUIRES esp-dl)

set(v2_best_espdl "${CMAKE_CURRENT_LIST_DIR}/models/p4/v2_best.espdl")
if (EXISTS "${v2_best_espdl}")
    idf_build_get_property(component_targets __COMPONENT_TARGETS)
    if ("___idf_espressif__esp-dl" IN_LIST component_targets)
        idf_component_get_property(espdl_dir espressif__esp-dl COMPONENT_DIR)
    elseif ("___idf_esp-dl" IN_LIST component_targets)
        idf_component_get_property(espdl_dir esp-dl COMPONENT_DIR)
    endif()

    if (espdl_dir)
        set(cmake_dir "${espdl_dir}/fbs_loader/cmake")
        include("${cmake_dir}/utilities.cmake")
        target_add_aligned_binary_data(${COMPONENT_LIB} "${v2_best_espdl}" BINARY)
        target_compile_definitions(${COMPONENT_LIB} PRIVATE USE_EMBEDDED_ESPDL_MODEL=1)
    endif()
endif()
