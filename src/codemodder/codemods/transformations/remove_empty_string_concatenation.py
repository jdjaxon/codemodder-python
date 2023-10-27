import libcst as cst
from libcst import CSTTransformer


class RemoveEmptyStringConcatenation(CSTTransformer):
    """
    Removes concatenation with empty strings (e.g. "hello " + "") or "hello" ""
    """

    def leave_BinaryOperation(
        self, original_node: cst.BinaryOperation, updated_node: cst.BinaryOperation
    ) -> cst.BaseExpression:
        return self.handle_node(updated_node)

    def leave_ConcatenatedString(
        self,
        original_node: cst.ConcatenatedString,
        updated_node: cst.ConcatenatedString,
    ) -> cst.BaseExpression:
        return self.handle_node(updated_node)

    def handle_node(
        self, updated_node: cst.BinaryOperation | cst.ConcatenatedString
    ) -> cst.BaseExpression:
        match updated_node.left:
            # TODO f-string cases
            case cst.SimpleString() if updated_node.left.raw_value == "":
                match updated_node.right:
                    case cst.SimpleString() if updated_node.right.raw_value == "":
                        return cst.SimpleString(value='""')
                    case _:
                        return updated_node.right
        match updated_node.right:
            case cst.SimpleString() if updated_node.right.raw_value == "":
                match updated_node.left:
                    case cst.SimpleString() if updated_node.left.raw_value == "":
                        return cst.SimpleString(value='""')
                    case _:
                        return updated_node.left
        return updated_node