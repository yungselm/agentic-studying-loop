# C++ addendum

- Standard in `pack.yaml` (default C++20; `ASL_CXX_STD=c++23` for `std::expected`, needs GCC 13+ or
  a recent clang). `asl check` compiles with `-Wall -Wextra -Wpedantic -Wshadow -Werror` and
  AddressSanitizer + UBSan, and runs clang-tidy's Core Guidelines checks when installed. A card
  that only works by breaking these says why in `notes`.
- Solutions match `clang-format` (LLVM style, 4-space indent). `#include` the headers a card uses;
  no `using namespace std;`, no `main`. Concept `code:` examples are declarations (namespace scope).
- Comments: elision `// ...`, header `// src/<path>  (<role>)`, hint `// uses: ...`, stubs
  `// stubs (real: src/<file>)`. Tests are 2–3 plain `assert(...)`s.
- Builds on Rust: ask the C++ spelling of a Rust idea (`Box<T>` → `std::unique_ptr<T>`) and put
  where the analogy breaks in `notes` (a moved-from object still exists; nothing stops a
  dangling reference). Undefined behaviour is a good concept card: the code, *why UB*, the fix.
- Debugging cards: the compiler or sanitizer message on the front, cause + fix in one bold
  sentence (like Rust's borrow-checker cards).
- Third-party libraries (Qt, VTK, ITK, DCMTK, GoogleTest) go in the `_ext` file.
