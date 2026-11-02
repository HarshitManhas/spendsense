import pytest

torch = pytest.importorskip('torch')
from ai_expense_scanner.ml.model import ExpenseModel, ModelConfig

torch.set_num_threads(2)


def make_model():
    torch.manual_seed(42)
    return ExpenseModel(20, ModelConfig(height=32, width=32, dimension=32, heads=4, layers=1, feedforward=64, dropout=0, max_length=32))


def test_shapes_gradients_and_causality():
    model = make_model().eval()
    images = torch.rand(2, 3, 32, 32)
    tokens = torch.randint(4, 20, (2, 12))
    logits = model(images, tokens)
    assert logits.shape == (2, 12, 20)
    assert torch.isfinite(logits).all()
    altered = tokens.clone(); altered[:, 6:] = 5
    assert torch.allclose(logits[:, :6], model(images, altered)[:, :6], atol=1e-6)
    logits.square().mean().backward()
    assert model.encoder[0].weight.grad.abs().sum() > 0
    assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)


def test_generation_stops_at_eos_and_length_limit():
    model = make_model()
    with torch.no_grad():
        model.output.weight.zero_(); model.output.bias.zero_(); model.output.bias[2] = 100
    assert model.generate(torch.rand(2, 3, 32, 32)).shape == (2, 2)
    with torch.no_grad():
        model.output.bias[2] = 0; model.output.bias[4] = 100
    assert model.generate(torch.rand(1, 3, 32, 32), max_length=8).shape == (1, 8)


def test_tiny_synthetic_overfit_uses_visual_input():
    model = make_model()
    images = torch.stack([torch.zeros(3, 32, 32), torch.ones(3, 32, 32)])
    inputs = torch.tensor([[1, 4], [1, 5]])
    labels = torch.tensor([[4, 2], [5, 2]])
    optimizer = torch.optim.AdamW(model.parameters(), lr=.005)
    for _ in range(100):
        logits = model(images, inputs)
        loss = torch.nn.functional.cross_entropy(logits.flatten(0, 1), labels.flatten())
        optimizer.zero_grad(); loss.backward(); optimizer.step()
    assert model.generate(images, max_length=4).tolist() == [[1, 4, 2], [1, 5, 2]]
