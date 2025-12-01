High-level and design principles
SOLID principles: A set of five principles for object-oriented programming that leads to more flexible, understandable, and maintainable code.
Single Responsibility Principle (SRP): A module should have only one reason to change.
Open/Closed Principle (OCP): Software entities should be open for extension, but closed for modification.
Liskov Substitution Principle (LSP): Objects of a superclass should be replaceable with objects of its subclasses without affecting the correctness of the program.
Interface Segregation Principle (ISP): Clients should not be forced to depend upon interfaces that they do not use.
Dependency Inversion Principle (DIP): Modules should not depend on concrete implementations; instead, they should depend on abstractions.
Abstraction: Hiding complex implementation details and showing only the necessary parts of an object to reduce complexity.
Encapsulation: Bundling data and methods that operate on the data within a single unit, and restricting direct access to some of the object's components.
Separation of Concerns (SoC): Dividing a program into distinct sections, where each section addresses a separate concern or domain.
Design Patterns: Using proven solutions to common, recurring problems in software design. 

Code quality and readability
DRY (Don't Repeat Yourself): Avoid duplicating code; reuse it instead.
KISS (Keep It Simple, Stupid): Favor simple, straightforward solutions over complex ones.
YAGNI (You Ain't Gonna Need It): Avoid adding functionality until it is actually needed.
Readability: Write code that is easy for other humans to understand. Avoid overly clever or complex one-liners.
Naming: Use descriptive, meaningful names for variables and functions.
Documentation and commenting: Write comments to explain the "why," not just the "what," especially for complex logic.
Function size: Keep functions small and focused on a single task. 

Maintenance and testing
Testability: Design code to be easily tested, which often involves keeping complexity low.
Continuous refactoring: Improve code quality and structure over time without changing its external behavior.
Error handling: Make code robust by handling errors and unexpected situations gracefully.
Global dependencies: Minimize the use of global variables to reduce confusing state management. 
