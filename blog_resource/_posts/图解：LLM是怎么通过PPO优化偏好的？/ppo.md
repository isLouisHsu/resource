
$$
\phi = \argmax_{\phi} E_{s \sim p(s;\theta)} \frac{1}{2} \min \left(
   \underline{
      || r_t + \gamma V^{\pi}(s_{t+1}) - \tilde{V}^{\pi}(s_t) ||_2^2
   },
   \underline{
      || r_t + \gamma V^{\pi}(s_{t+1}) - \text{clip}(
         \tilde{V}^{\pi}(s_t), V^{\pi}_{min}, V^{\pi}_{max}
      ) ||_2^2
   }
\right)
$$

$$
\tilde{\theta} = \argmax_{\tilde{\theta}} E_{s \sim p(s;\theta), a \sim \pi(a|s;\theta)} \min \left(
   \underline{
      \frac{\pi(a|s;\tilde{\theta})}{\pi(a|s; \theta)} A(s, a; \theta),
   },
   \underline{
      \text{clip} (
         \frac{\pi(a|s;\tilde{\theta})}{\pi(a|s; \theta)}, 1 - \epsilon, 1 + \epsilon
      ) A(s, a; \theta)
   }
\right)
$$
