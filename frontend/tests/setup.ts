import { configure } from "@testing-library/react";

// findBy*/waitFor default to 1 s, which parallel test files under load can
// exceed; a longer ceiling only slows down a test that is failing anyway.
configure({ asyncUtilTimeout: 5000 });
